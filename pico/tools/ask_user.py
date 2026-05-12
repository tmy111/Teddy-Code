"""User clarification tool definitions."""

ASK_USER_TOOL_SPECS = {
    "ask_user": {
        "schema": {"question": "str", "choices": "list[str]=[]"},
        "risky": False,
        "description": "Ask the interactive user a real blocking clarification question.",
    },
}

ASK_USER_TOOL_EXAMPLES = {
    "ask_user": '<tool>{"name":"ask_user","args":{"question":"Which target should I deploy?","choices":["staging","production"]}}</tool>',
}


def validate_ask_user_tool(name, args):
    if not str(args.get("question", "")).strip():
        raise ValueError("question must not be empty")
    choices = args.get("choices", [])
    if choices is not None and not isinstance(choices, list):
        raise ValueError("choices must be a list")


def tool_ask_user(agent, args):
    return agent.ask_user(str(args["question"]), choices=args.get("choices", []) or [])
