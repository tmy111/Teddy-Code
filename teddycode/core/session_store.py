# 负责 session JSON 文件的读写、列表和 latest 查找。
"""Session JSON storage."""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from .workspace import clip


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


class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        os.makedirs(_fs_path(self.root), exist_ok=True)
        self._lock = threading.RLock()

    def path(self, session_id):
        return self.root / f"{_safe_session_id(session_id)}.json"

    def event_path(self, session_id):
        return self.root / f"{_safe_session_id(session_id)}.events.jsonl"

    def save(self, session):
        path = self.path(session["id"])
        payload = json.dumps(session, indent=2)
        with self._lock:
            tmp_path = path.with_name(
                f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with open(_fs_path(tmp_path), "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(_fs_path(tmp_path), _fs_path(path))
        return path

    def load(self, session_id):
        with self._lock:
            with open(_fs_path(self.path(session_id)), encoding="utf-8") as handle:
                return json.load(handle)

    def latest(self):
        files = sorted(self.root.glob("*.json"), key=lambda path: path.stat().st_mtime)
        return files[-1].stem if files else None

    def list_sessions(self):
        rows = []
        for index, path in enumerate(
            sorted(
                self.root.glob("*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            ),
            start=1,
        ):
            try:
                with open(_fs_path(path), encoding="utf-8") as handle:
                    session = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            history = list(session.get("history", []))
            rows.append(
                {
                    "index": index,
                    "id": str(session.get("id", path.stem)),
                    "created_at": str(session.get("created_at", "")),
                    "updated_at": datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat(timespec="seconds"),
                    "history_count": len(history),
                    "runtime_mode": str(
                        session.get("runtime_mode", {}).get("mode", "default")
                        or "default"
                    ),
                    "workspace_root": str(session.get("workspace_root", "")),
                    "last_final_answer": _last_final_preview(history),
                }
            )
        return rows


def _last_final_preview(history):
    for item in reversed(history):
        if item.get("role") == "assistant":
            return clip(item.get("content", ""), 80)
    return ""


def _safe_session_id(session_id):
    value = str(session_id or "").strip()
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("invalid session id")
    return value
