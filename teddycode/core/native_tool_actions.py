"""Normalize native model tool calls into TeddyCode engine actions."""


def model_request_options(agent, prompt_metadata):
    options = {}
    native_tools = agent.native_tools()
    if native_tools:
        options["tools"] = native_tools
    if getattr(agent.model_client, "supports_prompt_cache", False):
        options.update(
            prompt_cache_key=prompt_metadata.get("prompt_cache_key"),
            prompt_cache_retention="in_memory",
        )
    else:
        options.update(prompt_cache_key=None, prompt_cache_retention=None)
    return options


def resolve_model_action(result, native_tools, parse_legacy):
    calls = tuple(getattr(result, "tool_calls", ()) or ())
    if calls:
        payloads = [_tool_payload(call) for call in calls]
        kind = "tool" if len(payloads) == 1 else "tools"
        return kind, payloads[0] if kind == "tool" else payloads, len(calls)

    raw_text = str(getattr(result, "text", "") or "").strip()
    if not native_tools:
        kind, payload = parse_legacy(raw_text)
        return kind, payload, 0
    if "<tool" in raw_text or "<final>" in raw_text:
        kind, payload = parse_legacy(raw_text)
        return kind, payload, 0
    if raw_text:
        return "final", raw_text, 0
    return "retry", "Return a normal final answer or request a native tool call.", 0


def _tool_payload(call):
    if isinstance(call, dict):
        return {"name": str(call.get("name", "")), "args": dict(call.get("args", {}) or {})}
    return {
        "name": str(getattr(call, "name", "")),
        "args": dict(getattr(call, "args", {}) or {}),
    }
