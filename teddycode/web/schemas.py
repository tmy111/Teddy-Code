"""HTTP request and response schemas for the local Web API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CreateSessionRequest(BaseModel):
    session_id: str | None = None
    resume: str | None = None
    approval: Literal["ask", "auto", "never"] | None = None

    @model_validator(mode="after")
    def validate_target(self):
        if self.session_id and self.resume:
            raise ValueError("session_id cannot be combined with resume")
        return self


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)


class ApprovalDecision(BaseModel):
    decision: Literal["allow", "deny"]


class QuestionAnswer(BaseModel):
    answer: str


class SessionSummary(BaseModel):
    id: str
    created_at: str = ""
    updated_at: str = ""
    history_count: int = 0
    runtime_mode: str = "default"
    workspace_root: str = ""
    last_final_answer: str = ""
    model: str = ""
    active: bool = False


class SessionDetail(SessionSummary):
    history: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceFile(BaseModel):
    path: str
    size: int
