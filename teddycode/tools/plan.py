"""Runtime mode tool definitions."""

PLAN_TOOL_SPECS = {
    "enter_plan_mode": {
        "schema": {"topic": "str", "path": "str?"},
        "risky": False,
        "description": "Enter plan mode for a named planning topic.",
    },
    "exit_plan_mode": {
        "schema": {},
        "risky": False,
        "description": "Exit plan mode and return to default runtime mode.",
    },
}

PLAN_TOOL_EXAMPLES = {
    "enter_plan_mode": '<tool>{"name":"enter_plan_mode","args":{"topic":"Refactor auth"}}</tool>',
    "exit_plan_mode": '<tool>{"name":"exit_plan_mode","args":{}}</tool>',
}



def tool_enter_plan_mode(agent, args):
    """让运行时进入计划模式，并返回当前计划文件路径。"""
    path = agent.enter_plan_mode(args["topic"], path=args.get("path"))
    return f"mode: plan\nplan path: {path}"


def tool_exit_plan_mode(agent, args):
    """退出计划模式，恢复默认运行模式。"""
    agent.exit_plan_mode()
    return "mode: default"
