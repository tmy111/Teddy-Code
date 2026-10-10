"""Credential-free adapter tests; Harbor remains an optional dependency.

Unit tests use an isolated Harbor interface double. The final integration
test uses the installed Harbor package when available, without containers.
"""

import asyncio
import functools
import importlib.util
import logging
import os
import shlex
import subprocess
import sys
import tarfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from teddycode import cli
from teddycode.config import resolve_provider_config
from teddycode.testing import ScriptedModelClient


ROOT = Path(__file__).resolve().parents[1]
INVALID_MODELS = [
    None, "", "gpt-test", "/model", "unknown/model", "OpenAI/model",
    "openai/", "anthropic/ ", "deepseek/\n", "openai/ model",
    "openai/model ", "openai/--help",
]


def load_adapter():
    spec = importlib.util.spec_from_file_location(
        "_teddycode_adapter_under_test", ROOT / "benchmarks/harbor_teddycode_agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def adapter(monkeypatch):
    """Keep interface doubles scoped to this fixture, never global imports."""
    class BaseInstalledAgent:
        pass

    def with_prompt_template(fn):
        @functools.wraps(fn)
        async def wrapper(self, instruction, *args, **kwargs):
            return await fn(self, self.render_instruction(instruction), *args, **kwargs)
        return wrapper

    for name in (
        "harbor", "harbor.agents", "harbor.agents.installed",
        "harbor.agents.installed.base", "harbor.environments",
        "harbor.environments.base", "harbor.models", "harbor.models.agent",
        "harbor.models.agent.context",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    base = sys.modules["harbor.agents.installed.base"]
    base.BaseInstalledAgent = BaseInstalledAgent
    base.with_prompt_template = with_prompt_template
    sys.modules["harbor.environments.base"].BaseEnvironment = object
    sys.modules["harbor.models.agent.context"].AgentContext = object
    return load_adapter()


def make_agent(adapter, model="openai/test-model"):
    agent = adapter.TeddyCodeAgent()
    agent.model_name = model
    agent.render_instruction = Mock(side_effect=lambda instruction: instruction)
    agent.exec_as_root = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    return agent


def test_archive_contains_every_checkout_module_and_build_metadata(adapter, tmp_path):
    destination = tmp_path / "source.tar.gz"
    assert adapter.make_source_archive(destination) == destination
    expected = {"pyproject.toml", "README.md"} | {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "teddycode").rglob("*.py")
        if "__pycache__" not in path.parts
    }
    with tarfile.open(destination) as archive:
        members = archive.getmembers()
        assert {member.name for member in members} == {f"teddycode/{p}" for p in expected}
        assert len(members) == len(expected)
        for member in members:
            assert member.isfile()
            relative = Path(member.name).relative_to("teddycode")
            assert not relative.is_absolute() and ".." not in relative.parts
            assert archive.extractfile(member).read() == (ROOT / relative).read_bytes()


@pytest.fixture
def source_checkout(adapter, monkeypatch, tmp_path):
    root = tmp_path / "checkout"
    for name in ("pyproject.toml", "README.md", "teddycode/__init__.py", "teddycode/cli.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
    monkeypatch.setattr(adapter, "ROOT", root)
    return root


def test_archive_excludes_credentials_state_tests_and_cache(adapter, source_checkout, tmp_path):
    for name in (
        ".env", ".teddycode.toml", "tests/test_secret.py", "artifacts/result.json",
        "teddycode/.env", "teddycode/__pycache__/cached.py", "teddycode/cache.pyc",
    ):
        path = source_checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("sensitive-or-generated", encoding="utf-8")
    destination = adapter.make_source_archive(tmp_path / "source.tar.gz")
    with tarfile.open(destination) as archive:
        assert set(archive.getnames()) == {
            "teddycode/pyproject.toml", "teddycode/README.md",
            "teddycode/teddycode/__init__.py", "teddycode/teddycode/cli.py",
        }


@pytest.mark.parametrize("name", ["README.md", "teddycode/cli.py", "teddycode/linked"])
def test_archive_rejects_symlinks(adapter, source_checkout, tmp_path, name):
    target = tmp_path / "outside"
    target.write_text("outside source", encoding="utf-8")
    path = source_checkout / name
    if path.exists():
        path.unlink()
    path.symlink_to(target)
    with pytest.raises(ValueError, match="symlinks"):
        adapter.make_source_archive(tmp_path / "source.tar.gz")


def test_archive_rejects_incomplete_checkout(adapter, source_checkout, tmp_path):
    (source_checkout / "teddycode/cli.py").unlink()
    with pytest.raises(ValueError, match="Missing required source"):
        adapter.make_source_archive(tmp_path / "source.tar.gz")


def test_archive_rejects_linked_package_directory(adapter, source_checkout, tmp_path):
    package = source_checkout / "teddycode"
    outside = tmp_path / "outside-package"
    package.rename(outside)
    package.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        adapter.make_source_archive(tmp_path / "source.tar.gz")


def test_install_uploads_complete_archive_before_root_execution(adapter):
    agent = make_agent(adapter)
    events = []
    uploaded = []

    async def upload(source, target):
        assert target == "/tmp/teddycode-source.tar.gz"
        with tarfile.open(source) as archive:
            assert "teddycode/teddycode/cli.py" in archive.getnames()
        uploaded.append(source)
        events.append("upload")

    async def execute(environment, **kwargs):
        assert not uploaded[0].exists()  # upload completed before temp cleanup
        assert kwargs["env"] == {"DEBIAN_FRONTEND": "noninteractive"}
        events.append("install")

    environment = types.SimpleNamespace(upload_file=AsyncMock(side_effect=upload))
    agent.exec_as_root.side_effect = execute
    asyncio.run(agent.install(environment))
    assert events == ["upload", "install"]
    agent.exec_as_agent.assert_not_awaited()


@pytest.mark.parametrize("failure", ["upload", "execute"])
def test_install_propagates_failures(adapter, failure):
    agent = make_agent(adapter)
    environment = types.SimpleNamespace(upload_file=AsyncMock())
    operation = environment.upload_file if failure == "upload" else agent.exec_as_root
    operation.side_effect = RuntimeError("installation failed")
    with pytest.raises(RuntimeError, match="installation failed"):
        asyncio.run(agent.install(environment))
    if failure == "upload":
        agent.exec_as_root.assert_not_awaited()


@pytest.mark.parametrize("scenario,success", [
    ("existing", True), ("missing-python", True), ("missing-venv", True),
    ("apt-fail", False), ("venv-fail", False), ("old-python", False),
    ("tar-fail", False), ("pip-fail", False), ("cli-fail", False),
])
def test_install_shell_fallbacks_and_fail_fast(adapter, tmp_path, scenario, success):
    agent = make_agent(adapter)
    asyncio.run(agent.install(types.SimpleNamespace(upload_file=AsyncMock())))
    command = agent.exec_as_root.await_args.kwargs["command"]
    assert "tar -xzf /tmp/teddycode-source.tar.gz -C /tmp/teddycode-source" in command
    assert "/opt/teddycode-venv/bin/pip install /tmp/teddycode-source/teddycode" in command
    # Intercept system operations; no apt, /opt writes, or package network calls.
    for executable, event in (("pip", "pip"), ("teddycode", "cli")):
        path = tmp_path / executable
        path.write_text(
            f'#!/bin/sh\necho "{event} $*" >> "$EVENT_LOG"\n'
            f'[ "$SCENARIO" != "{event}-fail" ]\n', encoding="utf-8"
        )
        path.chmod(0o755)
        command = command.replace(f"/opt/teddycode-venv/bin/{executable}", shlex.quote(str(path)))
    prelude = r'''
command() {
    if [ "$SCENARIO" = missing-python ] || [ "$SCENARIO" = apt-fail ]; then return 1; fi
    builtin command "$@"
}
apt-get() { echo "apt $*" >> "$EVENT_LOG"; [ "$SCENARIO" != apt-fail ]; }
venv_attempts=0
python3() {
    echo "python $*" >> "$EVENT_LOG"
    if [ "$1" = -c ]; then [ "$SCENARIO" != old-python ]; return; fi
    venv_attempts=$((venv_attempts + 1))
    if [ "$SCENARIO" = venv-fail ]; then return 1; fi
    if [ "$SCENARIO" = missing-venv ] && [ "$venv_attempts" = 1 ]; then return 1; fi
    return 0
}
mkdir() { echo mkdir >> "$EVENT_LOG"; }
tar() { echo tar >> "$EVENT_LOG"; [ "$SCENARIO" != tar-fail ]; }
'''
    log = tmp_path / "events"
    result = subprocess.run(
        ["bash", "-c", prelude + command], capture_output=True, text=True,
        env={**os.environ, "EVENT_LOG": str(log), "SCENARIO": scenario},
    )
    assert (result.returncode == 0) is success, result.stderr
    events = log.read_text().splitlines()
    if success:
        assert events[-2:] == ["pip install /tmp/teddycode-source/teddycode", "cli --help"]
    elif scenario not in {"pip-fail", "cli-fail"}:
        assert not any(event.startswith("pip ") for event in events)
    if scenario == "pip-fail":
        assert not any(event.startswith("cli ") for event in events)
    if scenario in {"missing-python", "missing-venv"}:
        assert any(event.startswith("apt install -y python3") for event in events)


@pytest.mark.parametrize("model", INVALID_MODELS)
def test_invalid_model_stops_before_upload_or_execution(adapter, model):
    agent = make_agent(adapter, model)
    environment = types.SimpleNamespace(upload_file=AsyncMock())
    with pytest.raises(ValueError, match="TeddyCode model"):
        asyncio.run(agent.run("task", environment, object()))
    environment.upload_file.assert_not_awaited()
    agent.exec_as_agent.assert_not_awaited()


@pytest.mark.parametrize("provider", ["openai", "anthropic", "deepseek"])
def test_run_uploads_utf8_prompt_and_matches_cli(adapter, monkeypatch, tmp_path, provider):
    model = "org/model';$(touch${IFS}/tmp/injected)"
    agent = make_agent(adapter, f"{provider}/{model}")
    instruction = "修复文件\n'quotes' ; $(echo unsafe)\n"
    rendered = "template\n" + instruction
    agent.render_instruction.return_value = rendered
    agent.render_instruction.side_effect = None
    uploads = []

    async def upload(source, target):
        assert source.read_text(encoding="utf-8") == rendered
        uploads.append((source, target))

    for key in list(os.environ):
        if key.startswith(("TEDDYCODE_", "OPENAI_", "ANTHROPIC_", "DEEPSEEK_")):
            monkeypatch.delenv(key)
    supplied = {
        "OPENAI_API_KEY": "fake-openai", "ANTHROPIC_API_KEY": "fake-anthropic",
        "DEEPSEEK_API_KEY": "fake-deepseek", "ANTHROPIC_AUTH_TOKEN": "fake-token",
        "OPENAI_API_BASE": "https://openai.invalid/v1",
        "ANTHROPIC_API_BASE": "https://anthropic.invalid",
        "DEEPSEEK_API_BASE": "https://deepseek.invalid/v1",
        "OPENAI_BASE_URL": "https://other-openai.invalid/v1",
        "ANTHROPIC_BASE_URL": "https://other-anthropic.invalid",
        "DEEPSEEK_BASE_URL": "https://other-deepseek.invalid/v1",
        "TEDDYCODE_API_KEY": "fake-generic", "TEDDYCODE_BASE_URL": "https://generic.invalid/v1",
    }
    for key, value in {**supplied, "GITHUB_PAT": "never-forward", "TEDDYCODE_MODEL": "wrong"}.items():
        monkeypatch.setenv(key, value)
    environment = types.SimpleNamespace(upload_file=AsyncMock(side_effect=upload))
    asyncio.run(agent.run(instruction, environment, object()))
    agent.render_instruction.assert_called_once_with(instruction)
    assert uploads[0][1] == "/tmp/teddycode-benchmark-prompt.txt"
    assert not uploads[0][0].exists()
    agent.exec_as_root.assert_not_awaited()
    call = agent.exec_as_agent.await_args
    assert call.args == (environment,)
    assert call.kwargs["env"] == supplied
    assert all(value not in call.kwargs["command"] for value in supplied.values())
    argv = shlex.split(call.kwargs["command"])
    assert argv[0] == "/opt/teddycode-venv/bin/teddycode"
    args = cli.build_arg_parser().parse_args(argv[1:])
    assert not cli.validate_args(args)
    assert cli.interaction_mode(args) == "one_shot"
    assert (args.provider, args.model) == (provider, model)
    assert (args.cwd, args.repo_root) == (".", ".")
    assert args.prompt_file == uploads[0][1]
    assert args.approval == "auto" and args.non_interactive and args.no_auto_dream
    assert args.final_readiness == "warn" and args.max_steps == 100
    config = resolve_provider_config(args.provider, model=args.model, start=tmp_path)
    assert config.model == model and config.api_key == "fake-generic"
    assert config.base_url == "https://generic.invalid/v1"


@pytest.mark.parametrize("provider,key_name", [
    ("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_AUTH_TOKEN"),
    ("deepseek", "DEEPSEEK_API_KEY"),
])
def test_native_credentials_and_base_aliases_match_cli(
    adapter, monkeypatch, tmp_path, provider, key_name,
):
    for key in list(os.environ):
        if key.startswith(("TEDDYCODE_", "OPENAI_", "ANTHROPIC_", "DEEPSEEK_")):
            monkeypatch.delenv(key)
    supplied = {key_name: "fake-key", f"{provider.upper()}_API_BASE": "https://test.invalid/v1"}
    for key, value in supplied.items():
        monkeypatch.setenv(key, value)
    agent = make_agent(adapter, f"{provider}/org/model")
    asyncio.run(agent.run("task", types.SimpleNamespace(upload_file=AsyncMock()), object()))
    assert agent.exec_as_agent.await_args.kwargs["env"] == supplied
    config = resolve_provider_config(provider, model="org/model", start=tmp_path)
    assert config.api_key == "fake-key" and config.base_url == "https://test.invalid/v1"


def test_prompt_upload_failure_prevents_task_start(adapter):
    agent = make_agent(adapter)
    environment = types.SimpleNamespace(upload_file=AsyncMock(side_effect=OSError("upload failed")))
    with pytest.raises(OSError, match="upload failed"):
        asyncio.run(agent.run("task", environment, object()))
    agent.exec_as_agent.assert_not_awaited()


def test_adapter_command_runs_real_cli_with_scripted_model(adapter, monkeypatch, tmp_path, capsys):
    """Map container paths locally and run the actual CLI/runtime without a model API."""
    for key in list(os.environ):
        if key.startswith(("TEDDYCODE_", "OPENAI_", "ANTHROPIC_", "DEEPSEEK_")):
            monkeypatch.delenv(key)
    (tmp_path / "sample.txt").write_text("before\n", encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    model = ScriptedModelClient([
        '<tool>{"name":"read_file","args":{"path":"sample.txt","start":1,"end":20}}</tool>',
        '<tool>{"name":"patch_file","args":{"path":"sample.txt","old_text":"before",'
        '"new_text":"after"}}</tool>',
        "<final>adapter task completed</final>",
    ])
    monkeypatch.setattr(cli, "_build_model_client", lambda args: model)
    agent = make_agent(adapter)

    async def upload(source, target):
        assert target == "/tmp/teddycode-benchmark-prompt.txt"
        prompt.write_bytes(source.read_bytes())

    async def execute(environment, *, command, env):
        assert env == {}
        argv = shlex.split(command)[1:]
        for flag, value in (
            ("--cwd", str(tmp_path)), ("--repo-root", str(tmp_path)),
            ("--prompt-file", str(prompt)),
        ):
            argv[argv.index(flag) + 1] = value
        assert cli.main(argv) == 0

    agent.exec_as_agent.side_effect = execute
    environment = types.SimpleNamespace(upload_file=AsyncMock(side_effect=upload))
    asyncio.run(agent.run("把 sample.txt 中的 before 改为 after。", environment, object()))
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "after\n"
    assert model.prompts and "adapter task completed" in capsys.readouterr().out


def test_run_without_credentials_and_exec_failure(adapter, monkeypatch):
    for key in list(os.environ):
        if key.startswith(("TEDDYCODE_", "OPENAI_", "ANTHROPIC_", "DEEPSEEK_")):
            monkeypatch.delenv(key)
    agent = make_agent(adapter)
    agent.exec_as_agent.side_effect = RuntimeError("agent failed")
    environment = types.SimpleNamespace(upload_file=AsyncMock())
    with pytest.raises(RuntimeError, match="agent failed"):
        asyncio.run(agent.run("task", environment, object()))
    assert agent.exec_as_agent.await_args.kwargs["env"] == {}


def test_installed_harbor_constructs_and_executes_adapter(tmp_path):
    pytest.importorskip("harbor.agents.installed.base", reason="optional Harbor integration")
    module = load_adapter()
    agent = module.TeddyCodeAgent(logs_dir=tmp_path, model_name="openai/test-model")
    agent.logger = logging.getLogger("test-harbor-adapter")
    environment = types.SimpleNamespace(
        upload_file=AsyncMock(),
        exec=AsyncMock(return_value=types.SimpleNamespace(return_code=0, stdout="", stderr="")),
    )
    asyncio.run(agent.install(environment))
    assert environment.exec.await_args.kwargs["user"] == "root"
    asyncio.run(agent.run("test instruction", environment, object()))
    assert environment.exec.await_count == 2
    assert environment.exec.await_args.kwargs["user"] is None
    environment.exec.return_value.return_code = 1
    with pytest.raises(RuntimeError):
        asyncio.run(agent.run("test instruction", environment, object()))
