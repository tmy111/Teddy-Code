import json
import shlex
import sys

from pico.testing import ScriptedModelClient
from pico import Pico, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs=None, **kwargs):
    (tmp_path / "README.md").write_text("hello world\n", encoding="utf-8")
    workspace = WorkspaceContext.build(tmp_path)
    store = SessionStore(tmp_path / ".pico" / "sessions")
    return Pico(
        model_client=ScriptedModelClient(outputs or []),
        workspace=workspace,
        session_store=store,
        approval_policy="auto",
        **kwargs,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_patch_requires_prior_fresh_read_and_allows_after_read(tmp_path):
    agent = build_agent(tmp_path)

    rejected = agent.run_tool("patch_file", {"path": "README.md", "old_text": "world", "new_text": "pico"})

    assert "read_file" in rejected
    assert agent._last_tool_result_metadata["tool_error_code"] == "prior_read_required"
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "hello world\n"

    agent.run_tool("read_file", {"path": "README.md", "start": 1, "end": 1})
    patched = agent.run_tool("patch_file", {"path": "README.md", "old_text": "world", "new_text": "pico"})

    assert patched == "patched README.md"
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "hello pico\n"


def test_write_file_allows_new_file_but_requires_read_before_overwrite(tmp_path):
    agent = build_agent(tmp_path)

    assert agent.run_tool("write_file", {"path": "notes.txt", "content": "new\n"}) == "wrote notes.txt (4 chars)"
    rejected = agent.run_tool("write_file", {"path": "README.md", "content": "overwrite\n"})

    assert "read_file" in rejected
    assert agent._last_tool_result_metadata["tool_error_code"] == "prior_read_required"

    agent.run_tool("read_file", {"path": "README.md", "start": 1, "end": 1})
    assert agent.run_tool("write_file", {"path": "README.md", "content": "overwrite\n"}) == "wrote README.md (10 chars)"


def test_patch_allows_self_authored_file_without_extra_read(tmp_path):
    agent = build_agent(tmp_path)

    assert agent.run_tool("write_file", {"path": "scripts/check.py", "content": "assert False\n"}) == "wrote scripts/check.py (13 chars)"
    patched = agent.run_tool(
        "patch_file",
        {"path": "scripts/check.py", "old_text": "assert False", "new_text": "assert True"},
    )

    assert patched == "patched scripts/check.py"
    assert (tmp_path / "scripts" / "check.py").read_text(encoding="utf-8") == "assert True\n"


def test_shell_search_like_commands_are_rejected_by_policy(tmp_path):
    agent = build_agent(tmp_path)

    rejected = agent.run_tool("run_shell", {"command": "grep -R hello .", "timeout": 20})

    assert "search" in rejected
    assert agent._last_tool_result_metadata["tool_error_code"] == "shell_search_should_use_tool"
    assert any(
        event["event"] == "tool_policy_decision"
        and event["tool_name"] == "run_shell"
        and event["decision"] == "deny"
        for event in read_jsonl(agent.session_event_bus.path)
    )


def test_shell_policy_allows_head_tail_grep_after_pipe(tmp_path):
    """`pip install ... 2>&1 | tail -5` 和 `git log | head -10` 是合法的输出管理，
    policy 不应该把它们当作 workspace search 拒绝。"""
    agent = build_agent(tmp_path)

    for command in (
        "echo hello && echo world | tail -1",
        "python3 --version 2>&1 | head -3",
        "echo a; echo b | grep b",
    ):
        result = agent.run_tool("run_shell", {"command": command, "timeout": 20})
        assert "exit_code: 0" in result, f"command should run, got: {result[:200]}"

    rejected_after_seq = agent.run_tool(
        "run_shell", {"command": "echo a; cat README.md", "timeout": 20}
    )
    assert "search" in rejected_after_seq, "命令分号后跟 cat 仍应被禁"
    assert agent._last_tool_result_metadata["tool_error_code"] == "shell_search_should_use_tool"


def test_long_shell_output_is_clipped_and_full_output_is_saved_as_run_artifact(tmp_path):
    script = "print('x'*6000)"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    agent = build_agent(
        tmp_path,
        [
            f'<tool>{{"name":"run_shell","args":{{"command":{json.dumps(command)},"timeout":20}}}}</tool>',
            "<final>captured</final>",
        ],
    )

    assert agent.ask("produce long shell output") == "captured"

    tool_item = next(item for item in agent.session["history"] if item["role"] == "tool" and item["name"] == "run_shell")
    assert len(tool_item["content"]) < 1200
    assert "full output saved:" in tool_item["content"]
    assert "full output saved:" in agent.model_client.prompts[1]

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    artifact_path = report["runtime_reminders"][0]["artifact_path"] if report["runtime_reminders"] else agent._last_tool_result_metadata["full_output_artifact"]
    full_output = (tmp_path / artifact_path).read_text(encoding="utf-8")
    assert "x" * 6000 in full_output

    trace_events = read_jsonl(agent.current_run_dir / "trace.jsonl")
    tool_event = next(event for event in trace_events if event["event"] == "tool_executed")
    assert tool_event["full_output_artifact"] == artifact_path
