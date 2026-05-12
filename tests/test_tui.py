import pytest

from pico import Pico, SessionStore, WorkspaceContext
from pico.testing import ScriptedModelClient


def build_agent(tmp_path, outputs, approval_policy="auto"):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    workspace = WorkspaceContext.build(tmp_path)
    return Pico(
        model_client=ScriptedModelClient(outputs),
        workspace=workspace,
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy=approval_policy,
    )


def assistant_contents(app):
    from pico.tui.widgets import AssistantMessage

    return [message.content for message in app.query(AssistantMessage)]


def rendered_text(widget) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


def test_cli_defaults_interactive_tty_mode_to_tui(monkeypatch):
    from pico.cli import build_arg_parser, interaction_mode

    monkeypatch.setattr(
        "pico.cli.sys.stdin", type("Stdin", (), {"isatty": lambda self: True})()
    )
    args = build_arg_parser().parse_args(["--cwd", "/tmp/workspace"])

    assert interaction_mode(args) == "tui"


def test_cli_keeps_prompt_as_one_shot_mode():
    from pico.cli import build_arg_parser, interaction_mode

    args = build_arg_parser().parse_args(["inspect", "tests"])

    assert interaction_mode(args) == "one_shot"


def test_cli_repl_flag_restores_plain_repl():
    from pico.cli import build_arg_parser, interaction_mode

    args = build_arg_parser().parse_args(["--repl", "--cwd", "/tmp/workspace"])

    assert interaction_mode(args) == "repl"


def test_cli_uses_plain_repl_for_piped_stdin(monkeypatch):
    from pico.cli import build_arg_parser, interaction_mode

    monkeypatch.setattr(
        "pico.cli.sys.stdin", type("Stdin", (), {"isatty": lambda self: False})()
    )
    args = build_arg_parser().parse_args(["--cwd", "/tmp/workspace"])

    assert interaction_mode(args) == "repl"


def test_cli_accepts_explicit_tui_flag():
    from pico.cli import build_arg_parser, interaction_mode

    args = build_arg_parser().parse_args(["--tui", "--cwd", "/tmp/workspace"])

    assert args.tui is True
    assert interaction_mode(args) == "tui"
    assert args.cwd == "/tmp/workspace"


def test_status_bar_shows_runtime_identity(tmp_path):
    from pico.tui.widgets import StatusBar

    agent = build_agent(tmp_path, [])
    status = StatusBar()

    status.update_agent(agent)

    text = rendered_text(status)
    assert "mode default" in text
    assert "session" in text


def test_status_bar_reads_context_usage_governance_fields():
    from pico.tui.widgets import StatusBar

    status = StatusBar()

    status.update_context_usage(
        {
            "total_estimated_tokens": 1234,
            "context_window": 200000,
            "free_tokens": 198766,
        }
    )

    assert "context 1234/200000" in rendered_text(status)


def test_cli_plan_mode_and_session_commands_expose_runtime_state(tmp_path):
    from pico.cli import handle_repl_command

    agent = build_agent(tmp_path, [])

    handled, should_exit, output = handle_repl_command(agent, "/plan refactor-auth")

    assert handled is True
    assert should_exit is False
    assert "mode: plan" in output
    assert ".pico/plans/refactor-auth-plan.md" in output
    assert agent.runtime_mode == "plan"

    handled, _, output = handle_repl_command(agent, "/mode")
    assert handled is True
    assert "runtime mode: plan" in output
    assert "plan path: .pico/plans/refactor-auth-plan.md" in output

    handled, _, output = handle_repl_command(agent, "/session")
    assert handled is True
    assert "session id:" in output
    assert "events path:" in output
    assert "runtime mode: plan" in output
    assert "worker summary:" in output

    handled, _, output = handle_repl_command(agent, "/plan-exit")
    assert handled is True
    assert output == "mode: default"
    assert agent.runtime_mode == "default"


def test_slash_command_registry_suggests_and_parses_subagent():
    from pico.commands.slash import (
        parse_subagent_args,
        resolve_command,
        suggest_commands,
    )

    suggestions = suggest_commands("/sub")

    assert suggestions[0].name == "subagent"
    assert resolve_command("sub").name == "subagent"

    payload, error = parse_subagent_args("worker --scope README.md,src update docs")

    assert error == ""
    assert payload["subagent_type"] == "worker"
    assert payload["write_scope"] == ["README.md", "src"]
    assert payload["prompt"] == "update docs"

    skill_suggestions = [command.name for command in suggest_commands("/sk")]
    assert "skills" in skill_suggestions
    assert "skill" in skill_suggestions


@pytest.mark.asyncio
async def test_tui_slash_suggestions_complete_partial_command(tmp_path):
    from pico.tui.app import PicoTuiApp
    from pico.tui.widgets import InputBar, SlashSuggestions

    app = PicoTuiApp(build_agent(tmp_path, []))

    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.input.value = "/sub"
        bar.update_slash_suggestions()

        suggestions = app.query_one(SlashSuggestions)
        assert suggestions.visible is True
        assert "/subagent" in rendered_text(suggestions)

        await pilot.press("tab")
        await pilot.pause(delay=0.1)

        assert bar.input.value == "/subagent "
        assert suggestions.visible is False


def test_agents_slash_command_shows_worker_status(tmp_path):
    from pico.cli import handle_repl_command

    agent = build_agent(tmp_path, [])

    handled, should_exit, output = handle_repl_command(agent, "/agents")

    assert handled is True
    assert should_exit is False
    assert "worker summary:" in output


def test_subagent_slash_command_launches_explore_worker(tmp_path):
    from pico.cli import handle_repl_command

    agent = build_agent(tmp_path, ["<final>Subagent checked README.</final>"])

    handled, should_exit, output = handle_repl_command(
        agent, "/subagent explore inspect README"
    )

    assert handled is True
    assert should_exit is False
    assert "agent_1" in output
    assert "completed" in output or "started" in output


@pytest.mark.asyncio
async def test_tui_help_command_uses_existing_repl_commands(tmp_path):
    from pico.tui.app import PicoTuiApp
    from pico.tui.widgets import InputBar

    agent = build_agent(tmp_path, [])
    app = PicoTuiApp(agent)

    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.input.value = "/help"
        await pilot.press("enter")
        await pilot.pause(delay=0.1)

        text = "\n".join(assistant_contents(app))
        assert "Commands:" in text
        assert "/memory" in text


@pytest.mark.asyncio
async def test_tui_runs_agent_turn_and_renders_final_answer(tmp_path):
    from pico.tui.app import PicoTuiApp
    from pico.tui.widgets import InputBar

    agent = build_agent(tmp_path, ["<final>Done from TUI.</final>"])
    app = PicoTuiApp(agent)

    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.input.value = "ship it"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)

        assert "Done from TUI." in "\n".join(assistant_contents(app))


@pytest.mark.asyncio
async def test_tui_renders_tool_card_result(tmp_path):
    from pico.tui.app import PicoTuiApp
    from pico.tui.widgets import InputBar, ToolCard

    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="notes/result.txt"><content>ok\n</content></tool>',
            "<final>Wrote it.</final>",
        ],
    )
    app = PicoTuiApp(agent)

    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.input.value = "write a file"
        await pilot.press("enter")
        await pilot.pause(delay=0.5)

        cards = list(app.query(ToolCard))
        assert cards
        assert cards[-1].status == "success"
        assert (tmp_path / "notes" / "result.txt").read_text(encoding="utf-8") == "ok\n"


@pytest.mark.asyncio
async def test_tui_approval_prompt_controls_risky_tool(tmp_path):
    from pico.tui.app import PicoTuiApp
    from pico.tui.widgets import ConfirmPrompt, InputBar

    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="notes/result.txt"><content>ok\n</content></tool>',
            "<final>Wrote it.</final>",
        ],
        approval_policy="ask",
    )
    app = PicoTuiApp(agent)

    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.input.value = "write a file"
        await pilot.press("enter")
        await pilot.pause(delay=0.2)

        assert app.query_one(ConfirmPrompt)

        await pilot.press("right")
        await pilot.press("enter")
        await pilot.pause(delay=0.5)

        assert "Wrote it." in "\n".join(assistant_contents(app))
        assert (tmp_path / "notes" / "result.txt").read_text(encoding="utf-8") == "ok\n"


@pytest.mark.asyncio
async def test_tui_ask_user_prompt_returns_selected_choice(tmp_path):
    from pico.tui.app import PicoTuiApp
    from pico.tui.widgets import AskUserPrompt, InputBar

    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"ask_user","args":{"question":"Ship?","choices":["no","yes"]}}</tool>',
            "<final>User chose yes.</final>",
        ],
    )
    app = PicoTuiApp(agent)

    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.input.value = "ask before shipping"
        await pilot.press("enter")
        await pilot.pause(delay=0.2)

        assert app.query_one(AskUserPrompt)

        await pilot.press("right")
        await pilot.press("enter")
        await pilot.pause(delay=0.5)

        assert "User chose yes." in "\n".join(assistant_contents(app))
