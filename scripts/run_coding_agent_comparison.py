"""Run TeddyCode, Claude Code, and Codex on the same Harbor dataset."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS = {
    "teddycode": "benchmarks.harbor_teddycode_agent:TeddyCodeAgent",
    "claude-code": "claude-code",
    "codex": "codex",
}


def build_commands(args: argparse.Namespace) -> dict[str, list[str]]:
    common = [
        "harbor", "run", "-d", args.dataset,
        "-o", str(args.output), "-n", str(args.concurrency),
        "-k", str(args.attempts),
    ]
    if args.task_limit:
        common += ["-l", str(args.task_limit)]
    return {
        name: common + [
            "--job-name", f"{args.job_prefix}-{name}",
            "-a", agent, "-m", model,
        ]
        for name, agent, model in (
            ("teddycode", AGENTS["teddycode"], args.teddycode_model),
            ("claude-code", AGENTS["claude-code"], args.claude_model),
            ("codex", AGENTS["codex"], args.codex_model),
        )
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="terminal-bench/terminal-bench-2")
    parser.add_argument("--teddycode-model", required=True, help="provider/model")
    parser.add_argument("--claude-model", required=True, help="provider/model")
    parser.add_argument("--codex-model", required=True, help="provider/model")
    parser.add_argument("--task-limit", type=int, default=3, help="0 runs the full dataset")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("artifacts/harbor-jobs"))
    parser.add_argument(
        "--job-prefix",
        default=f"teddycode-comparison-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.task_limit < 0 or args.attempts < 1 or args.concurrency < 1:
        parser.error("task-limit must be >= 0; attempts and concurrency must be >= 1")
    if not args.teddycode_model.startswith(("openai/", "anthropic/", "deepseek/")):
        parser.error("--teddycode-model must be openai/model, anthropic/model, or deepseek/model")
    commands = build_commands(args)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": args.dataset,
        "task_limit": args.task_limit,
        "attempts": args.attempts,
        "concurrency": args.concurrency,
        "commands": commands,
        "status": {},
    }
    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return 0
    if shutil.which("harbor") is None:
        print("harbor executable not found; install Harbor first", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / f"{args.job_prefix}-manifest.json"
    for name, command in commands.items():
        print(f"Running {name}: {args.dataset}", flush=True)
        completed = subprocess.run(command, cwd=PROJECT_ROOT, env=os.environ.copy(), check=False)
        manifest["status"][name] = completed.returncode
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}")
    print(f"Inspect with: harbor view {args.output}")
    return 0 if all(code == 0 for code in manifest["status"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
