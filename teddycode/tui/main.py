from __future__ import annotations

"""teddycode-tui 命令入口。

这个入口复用 CLI 参数解析和 build_agent()，但禁止 one-shot prompt；
用户需要先进入 TUI，再在输入框里提问。
"""

import sys

from teddycode.cli import build_agent, build_arg_parser
from teddycode.tui.app import TeddyCodeTuiApp


def main(argv=None):
    """解析参数、构建 agent，并启动 Textual TUI。"""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.prompt:
        print("teddycode-tui does not accept one-shot prompts; start the TUI and type there.", file=sys.stderr)
        return 2
    agent = build_agent(args)
    TeddyCodeTuiApp(agent).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
