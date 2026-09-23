"""Checks for the shared Harbor run configuration."""

import argparse

from scripts.run_coding_agent_comparison import build_commands


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
