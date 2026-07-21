"""Coordinator subagent tool definitions."""

from ..core.worker_manager import dumps_payload

AGENT_TOOL_NAMES = {"agent", "send_message", "task_stop"}

AGENT_TOOL_SPECS = {
    "agent": {
        "schema": {
            "description": "str",
            "prompt": "str",
            "subagent_type": "str='worker'",
            "write_scope": "list[str]=[]",
        },
        "risky": False,
        "description": "Launch a bounded worker or read-only Explore subagent.",
    },
    "send_message": {
        "schema": {"to": "str", "message": "str"},
        "risky": False,
        "description": "Continue an existing idle worker by id.",
    },
    "task_stop": {
        "schema": {"task_id": "str"},
        "risky": False,
        "description": "Stop a worker by id.",
    },
}

AGENT_TOOL_EXAMPLES = {
    "agent": '<tool>{"name":"agent","args":{"description":"Inspect auth","prompt":"Find auth entry points","subagent_type":"Explore"}}</tool>',
    "send_message": '<tool>{"name":"send_message","args":{"to":"agent_1","message":"Now patch the bug in src/auth.py"}}</tool>',
    "task_stop": '<tool>{"name":"task_stop","args":{"task_id":"agent_1"}}</tool>',
}


def validate_agent_runtime(agent, name, args):
    """校验子 agent 工具在当前运行模式下是否允许使用。"""
    if name == "agent":
        subagent_type = str(args.get("subagent_type", "worker")).strip()
        if agent.runtime_mode == "plan" and subagent_type != "Explore":
            raise ValueError("plan mode only allows Explore agents")


def tool_agent(agent, args):
    """启动一个有边界的 worker 或只读 Explore 子 agent。"""
    return dumps_payload(
        agent.worker_manager.spawn(
            args["description"],
            args["prompt"],
            subagent_type=args.get("subagent_type", "worker"),
            write_scope=args.get("write_scope", []),
        )
    )


def tool_send_message(agent, args):
    """向已有且空闲的子 agent 发送后续任务消息。"""
    return dumps_payload(agent.worker_manager.continue_task(args["to"], args["message"]))


def tool_task_stop(agent, args):
    """请求停止指定 id 的子 agent 任务。"""
    return dumps_payload(agent.worker_manager.stop_task(args["task_id"]))
