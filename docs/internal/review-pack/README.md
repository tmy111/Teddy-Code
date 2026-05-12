# Pico Review Pack

## Project pitch

Pico is a small local coding agent that turns one user request into a bounded
repository session: it builds context from the workspace, calls a provider,
executes approved tools, and persists the session locally.

## Architecture map

- `Pico` owns session state, memory, tools, and workspace safety.
- `Engine` drives the model/tool/final-answer loop.
- `SessionEventBus` writes the durable session timeline.
- `RunStore` keeps per-run traces, task state, and reports.
- `WorkerManager` keeps subagent task ids, continuation state, notifications,
  and write-scope boundaries.
- Provider clients live behind one `complete()` contract.

## Benchmark evidence

Use the test suite as the current acceptance floor. Real-session behavior should
be validated through persisted `.pico/sessions/*.json` and
`.pico/sessions/*.events.jsonl` artifacts before treating a runtime change as
done.

## Sample run artifact list

- `.pico/sessions/<session_id>.json`
- `.pico/sessions/<session_id>.events.jsonl`
- `.pico/runs/<run_id>/task_state.json`
- `.pico/runs/<run_id>/trace.jsonl`
- `.pico/runs/<run_id>/report.json`
