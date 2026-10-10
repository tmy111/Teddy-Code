"""Harbor installed-agent adapter for the current TeddyCode checkout.

Pass ``benchmarks.harbor_teddycode_agent:TeddyCodeAgent`` to ``harbor run -a``.
Harbor is an optional evaluation dependency, not a runtime dependency of TeddyCode.
"""

from __future__ import annotations

import os
import shlex
import tarfile
import tempfile
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from teddycode.config import ENV_API_KEY, ENV_BASE_URL, PROVIDER_ENV_NAMES


ROOT = Path(__file__).resolve().parents[1]


def make_source_archive(destination: Path) -> Path:
    """Package only installable source files from this checkout."""
    required = [ROOT / name for name in (
        "pyproject.toml", "README.md", "teddycode/__init__.py", "teddycode/cli.py",
    )]
    paths = sorted((ROOT / "teddycode").rglob("*"))
    for path in [ROOT / "teddycode", *required, *paths]:
        if path.is_symlink():
            raise ValueError(f"Source archive cannot include symlinks: {path}")
    for path in required:
        if not path.is_file():
            raise ValueError(f"Missing required source file: {path}")
    with tarfile.open(destination, "w:gz") as archive:
        for name in ("pyproject.toml", "README.md"):
            archive.add(ROOT / name, arcname=f"teddycode/{name}", recursive=False)
        for path in paths:
            if path.is_file() and path.suffix == ".py" and "__pycache__" not in path.parts:
                archive.add(
                    path, arcname=f"teddycode/{path.relative_to(ROOT).as_posix()}",
                    recursive=False,
                )
    return destination


class TeddyCodeAgent(BaseInstalledAgent):
    @staticmethod
    def name() -> str:
        return "teddycode"

    async def install(self, environment: BaseEnvironment) -> None:
        with tempfile.TemporaryDirectory(prefix="teddycode-harbor-") as directory:
            archive = make_source_archive(Path(directory) / "teddycode.tar.gz")
            await environment.upload_file(archive, "/tmp/teddycode-source.tar.gz")
        await self.exec_as_root(
            environment,
            command=(
                "set -e; "
                "command -v python3 >/dev/null || "
                "(apt-get update && apt-get install -y python3 python3-venv python3-pip); "
                "python3 -m venv /opt/teddycode-venv || "
                "(apt-get update && apt-get install -y python3-venv && "
                "python3 -m venv /opt/teddycode-venv); "
                "python3 -c 'import sys; assert sys.version_info >= (3, 10), "
                "\"TeddyCode requires Python 3.10+\"'; "
                "mkdir -p /tmp/teddycode-source && "
                "tar -xzf /tmp/teddycode-source.tar.gz -C /tmp/teddycode-source && "
                "/opt/teddycode-venv/bin/pip install /tmp/teddycode-source/teddycode && "
                "/opt/teddycode-venv/bin/teddycode --help >/dev/null"
            ),
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )

    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        model_name = self.model_name or ""
        if "/" not in model_name:
            raise ValueError("TeddyCode model must be provider/model (for example openai/gpt-5.4)")
        provider, model = model_name.split("/", 1)
        if (
            provider not in {"openai", "anthropic", "deepseek"}
            or not model.strip() or model != model.strip() or model.startswith("-")
        ):
            raise ValueError(f"Unsupported TeddyCode model: {model_name}")
        prompt_path = "/tmp/teddycode-benchmark-prompt.txt"
        with tempfile.TemporaryDirectory(prefix="teddycode-prompt-") as directory:
            prompt = Path(directory) / "prompt.txt"
            prompt.write_text(instruction, encoding="utf-8")
            await environment.upload_file(prompt, prompt_path)
        # Pass provider credentials only to the agent phase. A fresh task
        # container gives each trial its own TeddyCode session and workspace.
        await self.exec_as_agent(
            environment,
            command=(
                "/opt/teddycode-venv/bin/teddycode "
                "--cwd . --repo-root . "
                f"--prompt-file {shlex.quote(prompt_path)} "
                f"--provider {shlex.quote(provider)} --model {shlex.quote(model)} "
                "--approval auto --non-interactive --no-auto-dream "
                "--final-readiness warn --max-steps 100"
            ),
            env={
                key: os.environ[key]
                for key in (
                    ENV_API_KEY, ENV_BASE_URL,
                    *(key for names in PROVIDER_ENV_NAMES.values()
                      for field in ("api_key", "base_url") for key in names[field]),
                )
                if key in os.environ
            },
        )
