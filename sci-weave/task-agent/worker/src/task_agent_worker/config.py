"""Worker runtime configuration injected by ``uv run --env-file .env``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerSettings:
    """Non-secret Worker settings; the API key is never exposed in results."""

    api_key: str | None
    base_url: str
    model: str
    home: Path
    home_configured: bool
    session_dir: str
    connection_scope: str

    @classmethod
    def from_environment(cls) -> "WorkerSettings":
        return cls(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", ""),
            model=os.environ.get("SCIWEAVE_WORKER_MODEL", ""),
            home=Path(os.environ.get("SCIWEAVE_WORKER_HOME", "")),
            home_configured=bool(os.environ.get("SCIWEAVE_WORKER_HOME")),
            session_dir=os.environ.get("SCIWEAVE_WORKER_SESSION_DIR", ""),
            connection_scope=os.environ.get("SCIWEAVE_WORKER_CONNECTION_SCOPE", ""),
        )

    def validate_for_model_call(self) -> None:
        if not self.api_key or self.api_key.startswith("replace-with-"):
            raise ValueError("DEEPSEEK_API_KEY must be configured")
        if not self.base_url.startswith("https://"):
            raise ValueError("DEEPSEEK_BASE_URL must use HTTPS")
        if not self.model.strip():
            raise ValueError("SCIWEAVE_WORKER_MODEL must be configured")
        if not self.home_configured:
            raise ValueError("SCIWEAVE_WORKER_HOME must be configured")
        if not self.session_dir or Path(self.session_dir).is_absolute():
            raise ValueError("SCIWEAVE_WORKER_SESSION_DIR must be relative")
