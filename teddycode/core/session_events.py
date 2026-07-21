# session 级事件总线，负责记录模型、工具和状态变化事件。
"""Session-level event bus.

The run trace is per-task and diagnostic. The session event bus is the durable,
coarse-grained timeline for the interactive session itself.
"""

import json
import os
from pathlib import Path

from .workspace import now


def _fs_path(path):
    path = Path(path)
    if os.name != "nt":
        return str(path)
    resolved = str(path.resolve())
    if resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved


class SessionEventBus:
    def __init__(self, session_id, path, redact=None):
        self.session_id = str(session_id)
        self.path = Path(path)
        self.redact = redact or (lambda value: value)
        os.makedirs(_fs_path(self.path.parent), exist_ok=True)

    def emit(self, event, payload=None):
        record = dict(payload or {})
        record["event"] = str(event)
        record["session_id"] = self.session_id
        record["created_at"] = now()
        record = self.redact(record)
        os.makedirs(_fs_path(self.path.parent), exist_ok=True)
        with open(_fs_path(self.path), "a", encoding="utf-8") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")
        return record
