#放置 Engine 主循环复用的工具调用、重试和控制流辅助函数。
"""Control-loop tool and retry helpers shared by Engine.

These helpers execute tool payloads and handle retry summaries while Engine
keeps the turn loop shape visible. Terminal-state policy lives in
completion_governance.
"""

import time

from ..providers.base import complete_model
from ..providers.errors import ProviderError
from .workspace import clip, now


def execute_tool_payload(engine, task_state, user_message, payload):
    agent = engine.runtime
    name = payload.get("name", "")
    args = payload.get("args", {})
    task_state.record_tool(name)
    tool_started_at = time.monotonic()
    agent.session_event_bus.emit(
        "tool_started", {"run_id": task_state.run_id, "tool_name": name, "args": args}
    )
    yield {"type": "tool_call", "run_id": task_state.run_id, "name": name, "args": args}

    tool_result = agent.run_tool(name, args)
    tool_metadata = dict(agent._last_tool_result_metadata or {})
    tool_duration_ms = int((time.monotonic() - tool_started_at) * 1000)
    agent.session_event_bus.emit(
        "tool_finished",
        {
            "run_id": task_state.run_id,
            "tool_name": name,
            "status": tool_metadata.get("tool_status", ""),
            "tool_error_code": tool_metadata.get("tool_error_code", ""),
            "workspace_changed": bool(tool_metadata.get("workspace_changed", False)),
            "affected_paths": list(tool_metadata.get("affected_paths", [])),
            "duration_ms": tool_duration_ms,
        },
    )
    history_item = {
        "role": "tool",
        "name": name,
        "args": args,
        "content": tool_result,
        "created_at": now(),
        "tool_status": str(tool_metadata.get("tool_status", "")),
        "tool_error_code": str(tool_metadata.get("tool_error_code", "")),
        "workspace_changed": bool(tool_metadata.get("workspace_changed", False)),
        "affected_paths": list(tool_metadata.get("affected_paths", []) or []),
    }
    if tool_metadata.get("full_output_artifact"):
        history_item.update(
            {
                "artifact_ref": tool_metadata["full_output_artifact"],
                "original_chars": int(tool_metadata.get("original_chars", 0) or 0),
                "content_sha256": str(tool_metadata.get("content_sha256", "")),
            }
        )
    if tool_metadata.get("media_refs"):
        history_item["media_refs"] = list(tool_metadata.get("media_refs", []) or [])
    agent.record(history_item)
    for notification in engine.drain_worker_notifications():
        yield {
            "type": "worker_notification",
            "run_id": getattr(agent, "current_run_id", ""),
            "content": notification,
        }
    agent.run_store.write_task_state(task_state)
    agent.emit_trace(
        task_state,
        "tool_executed",
        {
            "name": name,
            "args": args,
            "result": clip(tool_result, 500),
            "duration_ms": tool_duration_ms,
            **tool_metadata,
        },
    )
    checkpoint = agent.create_checkpoint(
        task_state, user_message, trigger="tool_executed"
    )
    agent.run_store.write_task_state(task_state)
    agent.emit_trace(
        task_state,
        "checkpoint_created",
        {"checkpoint_id": checkpoint["checkpoint_id"], "trigger": "tool_executed"},
    )
    yield {
        "type": "tool_result",
        "run_id": task_state.run_id,
        "name": name,
        "content": tool_result,
        "metadata": tool_metadata,
    }


def should_retry_model_error(exc, provider_retries):
    if not isinstance(exc, ProviderError):
        return False
    code = str(getattr(exc, "code", "") or "")
    if code not in {"empty_response"}:
        return False
    return provider_retries.get(code, 0) < 1


_STEP_LIMIT_SUMMARY_NOTICE = (
    "You have hit the per-turn tool budget (max_steps). Do not call any more tools. "
    "Right now, return a single <final>...</final> answer in the user's language that "
    "briefly covers: (1) what you accomplished this turn, (2) what remains undone, "
    "(3) how the user can continue (e.g., `/resume` then `继续`). Keep it concise."
)


def request_step_limit_summary(engine, task_state, user_message):
    """Ask the model to write a graceful step-limit summary.

    Returns the final text, or None if the model fails or refuses to comply.
    Side effects: emits a trace event but does NOT mutate session history —
    the caller decides whether to record the resulting final.
    """
    agent = engine.runtime
    started_at = time.monotonic()
    try:
        prompt, _ = agent._build_prompt_and_metadata(_STEP_LIMIT_SUMMARY_NOTICE)
        result = complete_model(
            agent.model_client, prompt, agent.max_new_tokens
        )
    except Exception as exc:
        agent.emit_trace(
            task_state,
            "step_limit_summary_failed",
            {"error": clip(str(exc), 200)},
        )
        return None
    raw = (result.text or "").strip() if result else ""
    kind, payload = agent.parse(raw)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    agent.emit_trace(
        task_state,
        "step_limit_summary",
        {"kind": kind, "duration_ms": duration_ms, "produced": bool(kind == "final")},
    )
    if kind == "final" and payload:
        return str(payload).strip()
    return None
