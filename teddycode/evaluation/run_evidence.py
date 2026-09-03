"""Read-only helpers for TeddyCode run/session evidence.

These helpers intentionally do not import or instantiate the TeddyCode runtime. They
only interpret files that a completed CLI/REPL/TUI run left under `.teddycode/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunEvidence:
    workspace: Path
    run_dir: Path | None
    report_path: Path | None
    trace_path: Path | None
    task_state_path: Path | None
    session_path: Path | None
    session_event_path: Path | None
    report: dict
    task_state: dict
    trace_events: list[dict]
    session_events: list[dict]

    @classmethod
    def latest(cls, workspace: Path) -> "RunEvidence":  # Return the latest.
        workspace = Path(workspace).resolve()
        run_dir = _latest_dir(workspace / ".teddycode" / "runs")
        report_path = _existing(run_dir / "report.json") if run_dir else None
        trace_path = _existing(run_dir / "trace.jsonl") if run_dir else None
        task_state_path = _existing(run_dir / "task_state.json") if run_dir else None
        session_path = _latest_file(workspace / ".teddycode" / "sessions", "*.json")
        session_event_path = _latest_file(workspace / ".teddycode" / "sessions", "*.events.jsonl")
        return cls(
            workspace=workspace,
            run_dir=run_dir,
            report_path=report_path,
            trace_path=trace_path,
            task_state_path=task_state_path,
            session_path=session_path,
            session_event_path=session_event_path,
            report=_read_json(report_path),
            task_state=_read_json(task_state_path),
            trace_events=_read_jsonl(trace_path),
            session_events=_read_jsonl(session_event_path),
        )

    @property
    def session_id(self) -> str:  # Return the session id.
        return self.session_path.stem if self.session_path else ""

    def status(self) -> str:  # Return the status.
        return str(self.report.get("status") or self.task_state.get("status") or "")

    def stop_reason(self) -> str:  # Stop reason.
        return str(self.report.get("stop_reason") or self.task_state.get("stop_reason") or "")

    def changed_paths(self) -> list[str]:  # Return the changed paths.
        task_changed = self.task_state.get("changed_paths") or []
        graph_changed = ((self.report.get("artifact_graph") or {}).get("changed_paths")) or []
        return list(dict.fromkeys([*task_changed, *graph_changed]))

    def tool_events(self, name: str | None = None) -> list[dict]:  # Return the tool events.
        events = [event for event in self.trace_events if event.get("event") == "tool_executed"]
        if name is None:
            return events
        return [event for event in events if self.tool_name(event) == name]

    def tool_names(self) -> list[str]:  # Return the tool names.
        return [self.tool_name(event) for event in self.tool_events()]

    def has_tools(self, *names: str) -> bool:  # Return whether has tools.
        seen = set(self.tool_names())
        return all(name in seen for name in names)

    def tool_error_codes(self, name: str | None = None) -> list[str]:  # Return the tool error codes.
        return [str(event.get("tool_error_code") or "") for event in self.tool_events(name)]

    def full_output_artifacts(self) -> list[str]:  # Return the full output artifacts.
        artifacts = [
            str(event.get("full_output_artifact") or "")
            for event in self.tool_events()
            if event.get("full_output_artifact")
        ]
        for reminder in self.report.get("runtime_reminders") or []:
            artifact = str(reminder.get("artifact_path") or "")
            if artifact:
                artifacts.append(artifact)
        return list(dict.fromkeys(artifacts))

    def runtime_reminder_contains(self, text: str) -> bool:  # Return the runtime reminder contains.
        haystack = json.dumps(self.report.get("runtime_reminders") or [], ensure_ascii=False)
        return str(text) in haystack

    def has_session_event(self, event_name: str, **fields) -> bool:  # Return whether has session event.
        for event in self.session_events:
            if event.get("event") != event_name:
                continue
            if all(event.get(key) == value for key, value in fields.items()):
                return True
        return False

    @staticmethod
    def tool_name(event: dict) -> str:  # Return the tool name.
        return str(event.get("name") or event.get("tool_name") or event.get("tool") or "")


def _latest_dir(root: Path) -> Path | None:  # Return the latest dir.
    if not root.exists():
        return None
    dirs = [path for path in root.iterdir() if path.is_dir()]
    return max(dirs, key=lambda path: path.stat().st_mtime) if dirs else None


def _latest_file(root: Path, pattern: str) -> Path | None:  # Return the latest file.
    if not root.exists():
        return None
    files = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else None


def _existing(path: Path) -> Path | None:  # Return the existing.
    return path if path.exists() else None


def _read_json(path: Path | None) -> dict:  # Read json.
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path | None) -> list[dict]:  # Read jsonl.
    if not path or not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
