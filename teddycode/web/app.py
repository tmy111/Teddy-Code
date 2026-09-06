"""FastAPI application exposing the shared TeddyCode runtime."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from ..bootstrap import TeddyCodeConfig
from .schemas import (
    ApprovalDecision,
    CreateSessionRequest,
    MessageRequest,
    QuestionAnswer,
    SessionDetail,
    SessionSummary,
    WorkspaceFile,
)
from .session_manager import SessionManager
from .streaming import stream_sse


def create_app(
    config: TeddyCodeConfig | None = None,
    *,
    manager: SessionManager | None = None,
) -> FastAPI:
    """Create a local-only Web API adapter around TeddyCode."""

    session_manager = manager or SessionManager(config or TeddyCodeConfig())
    app = FastAPI(title="TeddyCode Web API", version="0.1.0")
    app.state.session_manager = session_manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "workspace": str(session_manager.root)}

    @app.post("/api/sessions", response_model=SessionDetail)
    def create_session(request: CreateSessionRequest):
        try:
            session = session_manager.create_session(
                session_id=request.session_id,
                resume=request.resume,
                approval=request.approval,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session_manager.session_detail(str(session.agent.session["id"]))

    @app.get("/api/sessions", response_model=list[SessionSummary])
    def list_sessions():
        return session_manager.list_sessions()

    @app.get("/api/sessions/{session_id}", response_model=SessionDetail)
    def get_session(session_id: str):
        try:
            return session_manager.session_detail(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc

    @app.get("/api/sessions/{session_id}/history")
    def get_history(session_id: str):
        try:
            detail = session_manager.session_detail(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        return {"session_id": session_id, "history": detail["history"]}

    @app.post("/api/sessions/{session_id}/messages")
    def send_message(session_id: str, request: MessageRequest):
        try:
            session = session_manager.get_session(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        stream = session.start_turn(request.message.strip())
        if stream is None:
            raise HTTPException(status_code=409, detail="session already has an active turn")
        return StreamingResponse(
            stream_sse(stream),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/sessions/{session_id}/abort")
    def abort(session_id: str):
        try:
            session = session_manager.get_session(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        return {"aborted": session.abort()}

    @app.post("/api/sessions/{session_id}/approvals/{request_id}")
    def resolve_approval(
        session_id: str, request_id: str, request: ApprovalDecision
    ):
        try:
            session = session_manager.get_session(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        if not session.resolve(request_id, "approval", request.decision == "allow"):
            raise HTTPException(status_code=404, detail="approval request not found")
        return {"status": "resolved", "decision": request.decision}

    @app.post("/api/sessions/{session_id}/questions/{request_id}")
    def resolve_question(session_id: str, request_id: str, request: QuestionAnswer):
        try:
            session = session_manager.get_session(session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        if not session.resolve(request_id, "question", request.answer):
            raise HTTPException(status_code=404, detail="question request not found")
        return {"status": "resolved"}

    @app.get("/api/workspace")
    def workspace():
        return {
            "cwd": session_manager.workspace.cwd,
            "repo_root": session_manager.workspace.repo_root,
            "branch": session_manager.workspace.branch,
        }

    @app.get("/api/workspace/files", response_model=list[WorkspaceFile])
    def workspace_files():
        return session_manager.list_workspace_files()

    @app.get("/api/workspace/file", response_class=PlainTextResponse)
    def workspace_file(path: str = Query(min_length=1)):
        try:
            resolved = session_manager.resolve_workspace_path(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        if resolved.stat().st_size > 1_000_000:
            raise HTTPException(status_code=413, detail="file is too large")
        return resolved.read_text(encoding="utf-8", errors="replace")

    return app


app = create_app()
