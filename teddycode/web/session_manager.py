"""In-process local-user session ownership and turn concurrency control."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from ..bootstrap import TeddyCodeConfig, create_agent
from ..core.session_store import SessionStore
from ..core.workspace import WorkspaceContext
from .streaming import TurnStream


@dataclass
class PendingInteraction:
    request_id: str
    kind: str
    payload: dict[str, Any]
    event: threading.Event = field(default_factory=threading.Event)
    response: Any = None


class WebSession:
    """One TeddyCode agent plus its single-turn and interaction state."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.turn_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.active_run: TurnStream | None = None
        self.pending: dict[str, PendingInteraction] = {}
        self.agent.approve = self._approve
        self.agent.ask_user_callback = self._ask_user

    @property
    def active(self) -> bool:
        with self.state_lock:
            return self.active_run is not None

    def start_turn(self, message: str) -> TurnStream | None:
        if not self.turn_lock.acquire(blocking=False):
            return None
        self.agent.abort_requested = False
        stream = TurnStream(self.agent.engine.run_turn, message, self._finish_turn)
        with self.state_lock:
            self.active_run = stream
        stream.start()
        return stream

    def abort(self) -> bool:
        with self.state_lock:
            active = self.active_run is not None
            pending = list(self.pending.values())
        if not active:
            return False
        self.agent.abort_current_turn()
        for interaction in pending:
            interaction.response = False if interaction.kind == "approval" else ""
            interaction.event.set()
        return True

    def resolve(self, request_id: str, kind: str, response: Any) -> bool:
        with self.state_lock:
            interaction = self.pending.get(request_id)
            if interaction is None or interaction.kind != kind:
                return False
            self.pending.pop(request_id, None)
            interaction.response = response
            interaction.event.set()
            return True

    def summary(self, persisted: dict[str, Any] | None = None) -> dict[str, Any]:
        persisted = dict(persisted or {})
        session = self.agent.session
        return {
            "id": str(session["id"]),
            "created_at": str(session.get("created_at", "")),
            "updated_at": str(persisted.get("updated_at", "")),
            "history_count": len(session.get("history", [])),
            "runtime_mode": str(
                session.get("runtime_mode", {}).get("mode", "default") or "default"
            ),
            "workspace_root": str(session.get("workspace_root", "")),
            "last_final_answer": str(persisted.get("last_final_answer", "")),
            "model": str(getattr(self.agent.model_client, "model", "")),
            "active": self.active,
        }

    def _finish_turn(self, stream: TurnStream) -> None:
        with self.state_lock:
            if self.active_run is stream:
                self.active_run = None
            self.pending.clear()
        self.turn_lock.release()

    def _request_interaction(self, kind: str, payload: dict[str, Any]) -> Any:
        interaction = PendingInteraction(
            request_id=uuid.uuid4().hex,
            kind=kind,
            payload=dict(payload),
        )
        with self.state_lock:
            stream = self.active_run
            if stream is None:
                return False if kind == "approval" else ""
            self.pending[interaction.request_id] = interaction
            stream.emit(
                {
                    "type": f"{kind}_required",
                    "request_id": interaction.request_id,
                    **interaction.payload,
                }
            )
        interaction.event.wait()
        with self.state_lock:
            self.pending.pop(interaction.request_id, None)
        return interaction.response

    def _approve(self, name: str, args: dict[str, Any]) -> bool:
        decision = self._request_interaction(
            "approval", {"name": str(name), "args": dict(args or {})}
        )
        return bool(decision)

    def _ask_user(self, question: str, choices: list[str]) -> str:
        answer = self._request_interaction(
            "question",
            {"question": str(question), "choices": [str(item) for item in choices]},
        )
        return str(answer or "")


class SessionManager:
    """Create and lazily resume Web sessions from TeddyCode's existing store."""

    def __init__(
        self,
        config: TeddyCodeConfig,
        agent_factory: Callable[[TeddyCodeConfig], Any] = create_agent,
    ) -> None:
        self.config = config
        self.agent_factory = agent_factory
        self.workspace = WorkspaceContext.build(
            config.cwd, repo_root_override=config.repo_root
        )
        self.root = Path(self.workspace.repo_root).resolve()
        self.store = SessionStore(self.root / ".teddycode" / "sessions")
        self._sessions: dict[str, WebSession] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        *,
        session_id: str | None = None,
        resume: str | None = None,
        approval: str | None = None,
    ) -> WebSession:
        if session_id and resume:
            raise ValueError("session_id cannot be combined with resume")
        if resume and not self.store.path(resume).exists():
            raise FileNotFoundError(resume)
        target = resume or session_id
        with self._lock:
            if target and target in self._sessions:
                return self._sessions[target]
        agent_config = replace(
            self.config,
            session_id=session_id,
            resume=resume,
            approval=approval or self.config.approval,
            ask_user_callback=None,
        )
        web_session = WebSession(self.agent_factory(agent_config))
        with self._lock:
            self._sessions[str(web_session.agent.session["id"])] = web_session
        return web_session

    def get_session(self, session_id: str) -> WebSession:
        with self._lock:
            existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        return self.create_session(resume=session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        persisted = self.store.list_sessions()
        by_id = {row["id"]: row for row in persisted}
        with self._lock:
            loaded = dict(self._sessions)
        rows = []
        for row in persisted:
            session = loaded.get(row["id"])
            if session is None:
                rows.append({**row, "model": "", "active": False})
            else:
                rows.append(session.summary(row))
        for session_id, session in loaded.items():
            if session_id not in by_id:
                rows.append(session.summary())
        return rows

    def session_detail(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        persisted = next(
            (row for row in self.store.list_sessions() if row["id"] == session_id),
            None,
        )
        return {
            **session.summary(persisted),
            "history": list(session.agent.session.get("history", [])),
        }

    def resolve_workspace_path(self, raw_path: str) -> Path:
        candidate = (self.root / str(raw_path or "")).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes workspace") from exc
        return candidate

    def list_workspace_files(self, limit: int = 2000) -> list[dict[str, Any]]:
        rows = []
        ignored = {".git", ".teddycode", ".venv", "node_modules", "dist"}
        for path in self.root.rglob("*"):
            if any(part in ignored for part in path.relative_to(self.root).parts):
                continue
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(self.root)
            except ValueError:
                continue
            rows.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "size": path.stat().st_size,
                }
            )
            if len(rows) >= limit:
                break
        return rows
