"""Shared TeddyCode runtime construction for CLI, TUI, and Web entry points."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .config import load_project_env, resolve_project_sandbox_config
from .core.model_router import ModelClientRouter
from .core.runtime import TeddyCode
from .core.session_store import SessionStore
from .core.workspace import WorkspaceContext, now
from .features import memory as memorylib
from .providers.runtime import (
    ProviderClientClasses,
    ProviderRuntime,
    build_provider_runtime,
)


DEFAULT_SECRET_ENV_NAMES = (
    "TEDDYCODE_API_KEY",
    "TEDDYCODE_OPENAI_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_API_TOKEN",
    "TEDDYCODE_VISION_API_KEY",
    "TEDDYCODE_ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "TEDDYCODE_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "GITHUB_PAT",
    "GH_PAT",
)
SECRET_ENV_NAMES_VAR = "TEDDYCODE_SECRET_ENV_NAMES"


@dataclass
class TeddyCodeConfig:
    """Configuration shared by every TeddyCode presentation layer."""

    cwd: str = "."
    repo_root: str | None = None
    config: str | None = None
    provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    vision_provider: str | None = None
    vision_api_key: str | None = None
    vision_model: str | None = None
    vision_base_url: str | None = None
    vision_timeout: int | None = None
    openai_timeout: int = 300
    temperature: float = 0.2
    session_id: str | None = None
    resume: str | None = None
    approval: str = "ask"
    max_steps: int = 50
    max_new_tokens: int | None = None
    sandbox: str | None = None
    sandbox_backend: str | None = None
    secret_env_names: Sequence[str] = field(default_factory=tuple)
    memory_dir: str | None = None
    auto_dream: bool = True
    dream_interval: float = 24.0
    dream_min_sessions: int = 5
    ask_user_callback: Callable[[str, list[str]], str] | None = None
    final_readiness: str = "warn"

    @classmethod
    def from_namespace(cls, args: Any, **overrides: Any) -> "TeddyCodeConfig":
        """Translate an argparse-like object without coupling bootstrap to argparse."""

        values = {
            "cwd": getattr(args, "cwd", "."),
            "repo_root": getattr(args, "repo_root", None),
            "config": getattr(args, "config", None),
            "provider": getattr(args, "provider", None),
            "api_key": getattr(args, "api_key", None),
            "model": getattr(args, "model", None),
            "base_url": getattr(args, "base_url", None),
            "vision_provider": getattr(args, "vision_provider", None),
            "vision_api_key": getattr(args, "vision_api_key", None),
            "vision_model": getattr(args, "vision_model", None),
            "vision_base_url": getattr(args, "vision_base_url", None),
            "vision_timeout": getattr(args, "vision_timeout", None),
            "openai_timeout": getattr(args, "openai_timeout", 300),
            "temperature": getattr(args, "temperature", 0.2),
            "session_id": getattr(args, "session_id", None),
            "resume": getattr(args, "resume", None),
            "approval": getattr(args, "approval", "ask"),
            "max_steps": getattr(args, "max_steps", 50),
            "max_new_tokens": getattr(args, "max_new_tokens", None),
            "sandbox": getattr(args, "sandbox", None),
            "sandbox_backend": getattr(args, "sandbox_backend", None),
            "secret_env_names": tuple(getattr(args, "secret_env_names", ()) or ()),
            "memory_dir": getattr(args, "memory_dir", None),
            "auto_dream": not getattr(args, "no_auto_dream", False),
            "dream_interval": getattr(args, "dream_interval", 24.0),
            "dream_min_sessions": getattr(args, "dream_min_sessions", 5),
            "final_readiness": getattr(args, "final_readiness", "warn"),
        }
        values.update(overrides)
        return cls(**values)


def configured_secret_names(config: TeddyCodeConfig) -> list[str]:
    """Return secret environment variable names configured for redaction."""

    names = set(DEFAULT_SECRET_ENV_NAMES)
    names.update(str(name).upper() for name in config.secret_env_names)
    extra_names = os.environ.get(SECRET_ENV_NAMES_VAR, "")
    if extra_names.strip():
        names.update(
            item.strip().upper() for item in extra_names.split(",") if item.strip()
        )
    return sorted(names)


def create_agent(
    config: TeddyCodeConfig,
    *,
    client_classes: ProviderClientClasses | None = None,
    provider_runtime: ProviderRuntime | None = None,
    model_client: object | None = None,
) -> TeddyCode:
    """Build or resume a TeddyCode runtime for any presentation layer."""

    workspace = WorkspaceContext.build(config.cwd, repo_root_override=config.repo_root)
    store = SessionStore(workspace.repo_root + "/.teddycode/sessions")
    provider_runtime = provider_runtime or build_provider_runtime(
        config, client_classes=client_classes
    )
    model = provider_runtime.model_client if model_client is None else model_client
    model_client_router = (
        provider_runtime.model_client_router
        if model is provider_runtime.model_client
        else ModelClientRouter(model)
    )

    sandbox_config = resolve_project_sandbox_config(
        start=workspace.repo_root,
        config_path=config.config,
        mode=config.sandbox,
        backend=config.sandbox_backend,
    )
    load_project_env(workspace.repo_root, override=False)
    session_id = store.latest() if config.resume == "latest" else config.resume
    runtime_kwargs = {
        "model_client": model,
        "workspace": workspace,
        "session_store": store,
        "approval_policy": config.approval,
        "max_steps": config.max_steps,
        "max_new_tokens": provider_runtime.max_new_tokens,
        "secret_env_names": configured_secret_names(config),
        "memory_dir": config.memory_dir,
        "auto_dream": config.auto_dream,
        "dream_interval_hours": config.dream_interval,
        "dream_min_sessions": config.dream_min_sessions,
        "model_client_factory": provider_runtime.model_client_factory,
        "model_client_router": model_client_router,
        "sandbox_config": sandbox_config,
        "ask_user_callback": config.ask_user_callback,
        "final_readiness_mode": config.final_readiness,
    }
    if session_id:
        return TeddyCode.from_session(session_id=session_id, **runtime_kwargs)

    session = None
    if config.session_id:
        session_path = store.path(config.session_id)
        if session_path.exists():
            session = store.load(config.session_id)
        else:
            session = {
                "id": config.session_id,
                "created_at": now(),
                "workspace_root": workspace.repo_root,
                "history": [],
                "memory": memorylib.default_memory_state(),
            }
    return TeddyCode(session=session, **runtime_kwargs)
