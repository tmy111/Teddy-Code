# Pico Runtime Evidence Plane

Pico 的 Gate 3 目标不是再加一个调度器，而是把一次真实 session 的运行证据稳定沉淀下来。主循环仍然由 `Engine` 控制，工具仍然由 `ToolExecutor` 执行，权限仍然由 permission layer 决定。Evidence plane 只消费 trace event，派生出可复盘、可面试解释、可验收的状态。

## Boundary

`Pico.emit_trace()` 是入口。它把普通 trace payload 规范化成 span-like event：

- `trace_id` / `span_id` / `parent_span_id`
- `turn_id`
- `phase`
- `status`
- `duration_ms`
- `artifact_paths`
- `error_type`

这些字段先服务本地 `.pico/runs/<run>/trace.jsonl`，不是为了立刻接 OpenTelemetry 或 Langfuse。外部 exporter 可以后置。

## Consumers

Runtime consumers 从 trace 派生状态，写回 `TaskState`，最后进入 `task_state.json` 和 `report.json`。

```text
Engine / ToolExecutor
        |
        v
  Pico.emit_trace()
        |
        +--> trace.jsonl
        |
        +--> RuntimeConsumers
              |
              +--> artifact_graph
              +--> verifier_suggestions
              +--> runtime_reminders
```

`artifact_graph` 只做轻量分类：backend、frontend、docs、tests、dependencies、other，并提取 route/API 字符串。它不尝试做 IDE 级依赖分析。

`verifier_suggestions` 只给建议，不自动运行。比如检测到 `package.json` 的 `test/build` script，会建议 `npm test` 和 `npm run build`；检测到 Python tests，会建议 `uv run python -m pytest -q`。

`runtime_reminders` 记录失败或部分成功的工具事件，帮助后续 report 解释“为什么这轮没有完全顺利”，但不会改变 agent 行为。

## Why This Shape

pi-mono 的体验强在事件驱动：session 先产生结构化生命周期事件，再由 UI 和扩展消费事件。Pico 现在走同一条底层路线，但保持本地 harness 的体量：先稳定事件协议和本地工件，再决定要不要接 UI、exporter、session tree 或 provider fallback。

这个边界避免了两个问题：

- 不把 verifier 变成隐式自动执行，避免权限和耗时失控。
- 不让 consumer 反向控制主循环，避免出现第二套调度逻辑。

因此 Gate 3 的判断标准是：一次真实 session 结束后，report 能回答它改了什么、属于哪类 artifact、应该怎么验收、哪里失败过，而不是仅仅保存一串日志。
