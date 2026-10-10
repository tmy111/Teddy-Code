"""Checks for the shared Harbor run configuration."""

import argparse
import json

import pytest

from scripts.run_coding_agent_comparison import build_commands, main


def test_three_agents_share_dataset_and_trial_budget():
    args = argparse.Namespace(
        dataset="terminal-bench/terminal-bench-2",
        output="jobs",
        concurrency=2,
        attempts=3,
        task_limit=5,
        job_prefix="comparison",
        teddycode_model="deepseek/deepseek-chat",
        claude_model="anthropic/claude-sonnet-4-6",
        codex_model="openai/gpt-5.4",
    )
    commands = build_commands(args)

    assert set(commands) == {"teddycode", "claude-code", "codex"}
    for command in commands.values():
        assert command[command.index("-d") + 1] == args.dataset
        assert command[command.index("-l") + 1] == "5"
        assert command[command.index("-k") + 1] == "3"
        assert command[command.index("-n") + 1] == "2"
    assert commands["teddycode"][commands["teddycode"].index("-a") + 1] == (
        "benchmarks.harbor_teddycode_agent:TeddyCodeAgent"
    )


def comparison_args(model):
    return [
        "--teddycode-model", model,
        "--claude-model", "anthropic/test-model",
        "--codex-model", "openai/test-model", "--dry-run",
    ]


@pytest.mark.parametrize("model", [
    "", "model", "/model", "other/model", "openai/", "anthropic/ ",
    "deepseek/\n", "openai/ model", "openai/model ", "openai/--help",
])
def test_comparison_rejects_invalid_teddycode_model(model):
    with pytest.raises(SystemExit) as error:
        main(comparison_args(model))
    assert error.value.code == 2


@pytest.mark.parametrize("provider", ["openai", "anthropic", "deepseek"])
def test_dry_run_full_dataset_without_harbor_or_credentials(provider, capsys):
    assert main(comparison_args(f"{provider}/org/model") + ["--task-limit", "0"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["task_limit"] == 0 and manifest["status"] == {}
    assert all("-l" not in command for command in manifest["commands"].values())
    assert manifest["commands"]["teddycode"][-1] == f"{provider}/org/model"
