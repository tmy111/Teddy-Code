"""Command-line launcher for the local TeddyCode Web API."""

from __future__ import annotations

import argparse

from ..bootstrap import TeddyCodeConfig
from .app import create_app


def build_web_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local TeddyCode Web API.")
    parser.add_argument("--cwd", default=".", help="Workspace directory.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--approval", choices=("ask", "auto", "never"), default="ask")
    parser.add_argument("--sandbox", choices=("off", "best_effort", "required"))
    parser.add_argument("--sandbox-backend", choices=("auto", "bubblewrap", "none"))
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--openai-timeout", type=int, default=300)
    parser.add_argument("--no-auto-dream", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv=None) -> int:
    args = build_web_arg_parser().parse_args(argv)
    import uvicorn

    config = TeddyCodeConfig.from_namespace(args)
    uvicorn.run(create_app(config), host=args.host, port=args.port)
    return 0
