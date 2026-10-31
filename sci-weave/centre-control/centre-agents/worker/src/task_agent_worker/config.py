"""Worker runtime configuration injected by ``uv run --env-file .env``."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


def _required_worker_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise ValueError(f"{name} must be configured")
    return Path(value)


_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def ensure_relative_session_dir(value: str, message: str) -> None:
    """Reject a session dir that could escape the Worker home on either platform.

    ``Path(...).is_absolute()`` is not enough: on POSIX ``Path("C:/absolute")`` is
    relative and ``Path(r"..\\..\\outside")`` is a single path part, so both would
    slip through and land under the working directory instead of being refused
    (ai4-grlc). The checks are therefore textual as well as pathlib-based.
    """
    if not value or not value.strip():
        raise ValueError(message)
    if Path(value).is_absolute() or _DRIVE_PREFIX.match(value):
        raise ValueError(message)
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError(message)


@dataclass(frozen=True)
class WorkerSettings:
    """Non-secret Worker settings; the API key is never exposed in results."""

    api_key: str | None
    base_url: str
    model: str
    home: Path
    session_dir: str
    connection_scope: str

    @classmethod
    def from_environment(cls) -> "WorkerSettings":
        return cls(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", ""),
            model=os.environ.get("SCIWEAVE_WORKER_MODEL", ""),
            home=_required_worker_path("SCIWEAVE_WORKER_HOME"),
            session_dir=os.environ.get("SCIWEAVE_WORKER_SESSION_DIR", ""),
            connection_scope=os.environ.get("SCIWEAVE_WORKER_CONNECTION_SCOPE", ""),
        )

    def validate_runtime(self, *, require_api_key: bool = True) -> None:
        if require_api_key and (not self.api_key or self.api_key.startswith("replace-with-")):
            raise ValueError("DEEPSEEK_API_KEY must be configured")
        if require_api_key and not self.base_url.startswith("https://"):
            raise ValueError("DEEPSEEK_BASE_URL must use HTTPS")
        if require_api_key and not self.model.strip():
            raise ValueError("SCIWEAVE_WORKER_MODEL must be configured")
        # One refusal message for every escape shape. ``Path(...).is_absolute()``
        # answers differently per platform (``C:/x`` is absolute on Windows and
        # relative on POSIX), so branching on it here made the same bad value
        # produce two different messages depending on the OS; the textual checks
        # inside ``ensure_relative_session_dir`` are the platform-independent gate.
        ensure_relative_session_dir(
            self.session_dir, "SCIWEAVE_WORKER_SESSION_DIR must stay within Worker home"
        )
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.connection_scope):
            raise ValueError("SCIWEAVE_WORKER_CONNECTION_SCOPE has invalid characters")

    def validate_for_model_call(self) -> None:
        self.validate_runtime(require_api_key=True)
