"""命令行入口。

这个模块负责把“用户怎么启动 pico”翻译成 runtime 能理解的对象：
解析参数、挑模型后端、构建工作区快照、恢复或新建 session，
最后进入 one-shot 或交互式循环。
"""

import argparse
import json
import os
import shutil
import sys
import textwrap

from .config import DEFAULT_PROVIDER, PROVIDER_DEFAULTS, load_project_env, resolve_provider_config
from .features import skills as skillslib
from .features.skills_runtime import invoke_skill
from .providers import AnthropicCompatibleModelClient, OpenAICompatibleModelClient
from .core.runtime import Pico, SessionStore
from .core.workspace import WorkspaceContext, middle

DEFAULT_SECRET_ENV_NAMES = (
    "PICO_API_KEY",
    "PICO_OPENAI_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_API_TOKEN",
    "PICO_ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "PICO_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "PICO_RIGHT_CODES_API_KEY",
    "RIGHT_CODES_API_KEY",
    "GITHUB_PAT",
    "GH_PAT",
)

WELCOME_ART = (
    "        /\\___/\\\\",
    "       (  o o  )",
    "       /   ^   \\\\",
    "      /|       |\\\\",
)
WELCOME_NAME = "pico"
WELCOME_SUBTITLE = "local coding agent"
WELCOME_STATUS = "calm shell, ready for work"
HELP_DETAILS = textwrap.dedent(
    """\
    Commands:
    /help    Show this help message.
    /memory  Show the agent's distilled working memory.
    /skills  List available skills and slash workflows.
    /session Show the path to the saved session file.
    /context Show prompt context usage.
    /compact Compact older session history.
    /reset   Clear the current session history and memory.
    /exit    Exit the agent.
    """
).strip()


DEFAULT_OPENAI_MODEL = PROVIDER_DEFAULTS["openai"]["model"]
DEFAULT_OPENAI_BASE_URL = PROVIDER_DEFAULTS["openai"]["base_url"]
SECRET_ENV_NAMES_VAR = "PICO_SECRET_ENV_NAMES"


def _configured_secret_names(args):
    configured_secret_names = set(DEFAULT_SECRET_ENV_NAMES)
    configured_secret_names.update(str(name).upper() for name in args.secret_env_names)
    extra_names = os.environ.get(SECRET_ENV_NAMES_VAR, "")
    if extra_names.strip():
        configured_secret_names.update(
            item.strip().upper()
            for item in extra_names.split(",")
            if item.strip()
        )
    return sorted(configured_secret_names)


def _build_model_client(args):
    config = resolve_provider_config(
        getattr(args, "provider", None),
        start=getattr(args, "cwd", "."),
        config_path=getattr(args, "config", None),
        model=getattr(args, "model", None),
        base_url=getattr(args, "base_url", None),
        api_key=getattr(args, "api_key", None),
    )
    # CLI 只负责把 provider profile 翻译成具体协议 client。
    # 例如 deepseek 是 profile，protocol=anthropic 才决定走 Messages API。
    if config.protocol == "openai":
        return OpenAICompatibleModelClient(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", 300),
        )
    if config.protocol == "anthropic":
        return AnthropicCompatibleModelClient(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", 300),
        )

    raise ValueError(f"unknown provider protocol: {config.protocol}")


def build_welcome(agent, model, host):
    width = max(68, min(shutil.get_terminal_size((80, 20)).columns, 84))
    inner = width - 4
    gap = 3
    left_width = (inner - gap) // 2
    right_width = inner - gap - left_width

    def row(text):
        body = middle(text, width - 4)
        return f"| {body.ljust(width - 4)} |"

    def divider(char="-"):
        return "+" + char * (width - 2) + "+"

    def center(text):
        body = middle(text, inner)
        return f"| {body.center(inner)} |"

    def cell(label, value, size):
        body = middle(f"{label:<9} {value}", size)
        return body.ljust(size)

    def pair(left_label, left_value, right_label, right_value):
        left = cell(left_label, left_value, left_width)
        right = cell(right_label, right_value, right_width)
        return f"| {left}{' ' * gap}{right} |"

    line = divider("=")
    rows = [center(text) for text in WELCOME_ART]
    rows.extend(
        [
            center(WELCOME_NAME),
            center(WELCOME_SUBTITLE),
            center(WELCOME_STATUS),
            divider("-"),
            row(""),
            row("WORKSPACE  " + middle(agent.workspace.cwd, inner - 11)),
            pair("MODEL", model, "BRANCH", agent.workspace.branch),
            pair("APPROVAL", agent.approval_policy, "SESSION", agent.session["id"]),
            row(""),
        ]
    )
    return "\n".join([line, *rows, line])


def build_agent(args):
    """根据 CLI 参数装配出一个可运行的 Pico 实例。

    为什么存在：
    命令行参数只是字符串和开关，runtime 需要的是已经装配好的对象图：
    model client、workspace snapshot、session store、secret 配置等。
    这个函数负责把“启动参数”翻译成“agent 运行现场”。

    输入 / 输出：
    - 输入：`argparse` 解析后的 `args`
    - 输出：一个新的 `Pico`，或一个从旧 session 恢复出来的 `Pico`

    在 agent 链路里的位置：
    它是整个程序启动链路里最靠近 runtime 的装配点。`main()` 先调它，
    得到 agent 后，后面无论是 one-shot 还是 REPL 模式，都会落到 `ask()`。
    """
    # 这里是 CLI 到 runtime 的装配点：
    # 先采集工作区快照，再整理 secret 名单、模型后端和 session。
    workspace = WorkspaceContext.build(args.cwd)
    store = SessionStore(workspace.repo_root + "/.pico/sessions")
    model = _build_model_client(args)
    load_project_env(workspace.repo_root, override=False)
    configured_secret_names = _configured_secret_names(args)
    session_id = args.resume
    if session_id == "latest":
        session_id = store.latest()
    if session_id:
        return Pico.from_session(
            model_client=model,
            workspace=workspace,
            session_store=store,
            session_id=session_id,
            approval_policy=args.approval,
            max_steps=args.max_steps,
            max_new_tokens=args.max_new_tokens,
            secret_env_names=configured_secret_names,
        )
    return Pico(
        model_client=model,
        workspace=workspace,
        session_store=store,
        approval_policy=args.approval,
        max_steps=args.max_steps,
        max_new_tokens=args.max_new_tokens,
        secret_env_names=configured_secret_names,
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Minimal coding agent for provider profiles backed by OpenAI-compatible or Anthropic-compatible APIs.",
    )
    parser.add_argument("prompt", nargs="*", help="Optional one-shot prompt.")
    parser.add_argument("--cwd", default=".", help="Workspace directory.")
    parser.add_argument("--config", default=None, help="Path to a Pico TOML config file.")
    parser.add_argument("--provider", default=None, help=f"Provider profile to use. Defaults to config provider or {DEFAULT_PROVIDER}.")
    parser.add_argument("--api-key", default=None, help="API key override for the selected provider profile.")
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override for the selected provider profile.",
    )
    parser.add_argument("--base-url", default=None, help="API base URL override for the selected provider profile.")
    parser.add_argument("--openai-timeout", type=int, default=300, help="Provider request timeout in seconds.")
    parser.add_argument("--resume", default=None, help="Session id to resume or 'latest'.")
    parser.add_argument("--approval", choices=("ask", "auto", "never"), default="ask", help="Approval policy for risky tools.")
    parser.add_argument(
        "--secret-env-name",
        dest="secret_env_names",
        action="append",
        default=[],
        help="Extra environment variable names to treat as secrets for trace/report redaction.",
    )
    parser.add_argument("--max-steps", type=int, default=6, help="Maximum tool/model iterations per request.")
    parser.add_argument("--max-new-tokens", type=int, default=512, help="Maximum model output tokens per step.")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature sent to the provider.")
    return parser


def handle_repl_command(agent, user_input):
    if user_input in {"/exit", "/quit"}:
        return True, True, ""
    if user_input == "/help":
        return True, False, HELP_DETAILS
    if user_input == "/memory":
        return True, False, agent.memory_text()
    if user_input == "/skills":
        return True, False, skillslib.render_skills_list(agent.skills)
    if user_input == "/session":
        return True, False, str(agent.session_path)
    if user_input == "/context":
        return True, False, json.dumps(agent.prompt_metadata("", "")["context_usage"], indent=2, sort_keys=True)
    if user_input == "/compact":
        return True, False, json.dumps(agent.compact_history(trigger="manual"), indent=2, sort_keys=True)
    if user_input == "/reset":
        agent.reset()
        return True, False, "session reset"
    command, arguments = skillslib.parse_slash_command(user_input)
    if command and command in agent.skills:
        return True, False, invoke_skill(agent, command, arguments)
    return False, False, ""


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        agent = build_agent(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    model = getattr(agent.model_client, "model", getattr(args, "model", DEFAULT_OPENAI_MODEL))
    host = getattr(agent.model_client, "base_url", getattr(args, "base_url", DEFAULT_OPENAI_BASE_URL))
    print(build_welcome(agent, model=model, host=host))

    if args.prompt:
        # one-shot 模式：只跑一次 ask，不进入 REPL 循环。
        prompt = " ".join(args.prompt).strip()
        if prompt:
            print()
            try:
                handled, _, output = handle_repl_command(agent, prompt)
                print(output if handled else agent.ask(prompt))
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        return 0

    while True:
        # 交互模式：每次读取一条用户输入，交给同一个 agent，
        # 因此 session history 和 working memory 会跨轮延续。
        try:
            user_input = input("\npico> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if not user_input:
            continue
        handled, should_exit, output = handle_repl_command(agent, user_input)
        if should_exit:
            return 0
        if handled:
            print(output)
            continue

        print()
        try:
            print(agent.ask(user_input))
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
