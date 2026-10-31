"""Bridge configuration; every deployment value comes from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://sciencepal.ai/api"
DEFAULT_MAX_UPLOAD_MB = 25
DEFAULT_MAX_DOWNLOAD_MB = 100
DEFAULT_MAX_ARTIFACTS = 200


class ConfigError(ValueError):
    """Stable configuration error; the code is safe to show to an agent."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _int_env(
    env: dict[str, str],
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int = 10_000,
) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError("invalid_config", f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ConfigError("invalid_config", f"{name} is out of range")
    return value


@dataclass(frozen=True)
class BridgeConfig:
    base_url: str
    access_token: str
    workspace: Path
    run_db: Path
    max_upload_bytes: int
    max_download_bytes: int
    max_artifacts: int
    request_timeout_s: float
    default_agent_id: str | None
    # ai4-roow: write-back target and the identity the draft is submitted under.
    draft_buffer_url: str = ""
    draft_buffer_token: str = ""
    submitted_by: str = "sciencepal-bridge"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "BridgeConfig":
        env = os.environ if env is None else env
        base_url = (env.get("SCIENCEPAL_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
        if not (
            base_url.startswith("https://")
            or base_url.startswith("http://127.0.0.1")
            or base_url.startswith("http://localhost")
        ):
            raise ConfigError("invalid_config", "SCIENCEPAL_BASE_URL must be an https endpoint")

        workspace_raw = (env.get("SCIENCEPAL_WORKSPACE") or "").strip()
        workspace = (
            Path(workspace_raw).expanduser()
            if workspace_raw
            else Path.home() / ".sciweave" / "sciencepal-workspace"
        )
        workspace = workspace.resolve()
        run_db = Path(env.get("SCIENCEPAL_RUN_DB") or str(workspace / "runs.sqlite")).expanduser()
        if not run_db.is_absolute():
            run_db = (workspace / run_db).resolve()

        upload_mb = _int_env(env, "SCIENCEPAL_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB, minimum=1, maximum=200)
        download_mb = _int_env(env, "SCIENCEPAL_MAX_DOWNLOAD_MB", DEFAULT_MAX_DOWNLOAD_MB, minimum=1, maximum=1024)
        max_artifacts = _int_env(env, "SCIENCEPAL_MAX_ARTIFACTS", DEFAULT_MAX_ARTIFACTS, minimum=1, maximum=2000)

        return cls(
            base_url=base_url,
            access_token=(env.get("SCIENCEPAL_ACCESS_TOKEN") or "").strip(),
            workspace=workspace,
            run_db=run_db,
            max_upload_bytes=upload_mb * 1024 * 1024,
            max_download_bytes=download_mb * 1024 * 1024,
            max_artifacts=max_artifacts,
            request_timeout_s=30.0,
            default_agent_id=(env.get("SCIENCEPAL_DEFAULT_AGENT_ID") or "").strip() or None,
            draft_buffer_url=(env.get("SCIWEAVE_DRAFT_BUFFER_URL") or "").strip(),
            draft_buffer_token=(env.get("SCIWEAVE_DRAFT_BUFFER_TOKEN") or "").strip(),
            submitted_by=(env.get("SCIWEAVE_BRIDGE_SUBMITTED_BY") or "").strip() or "sciencepal-bridge",
        )

    def require_token(self) -> str:
        if not self.access_token:
            raise ConfigError("sciencepal_token_missing", "SCIENCEPAL_ACCESS_TOKEN is not configured")
        return self.access_token

    def ensure_workspace(self) -> Path:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.run_db.parent.mkdir(parents=True, exist_ok=True)
        return self.workspace

    def resolve_input(self, path: str) -> Path:
        self.ensure_workspace()
        # Re-resolve here rather than trusting ``self.workspace``: a config built
        # with a path that did not exist yet (or that carries an 8.3 short form
        # such as ``C:\Users\RUNNER~1\...``) keeps the raw spelling, while
        # ``resolve()`` on the input returns the long one. Comparing the two makes
        # every in-workspace input look like an escape on such a machine.
        workspace = self.workspace.resolve()
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = workspace / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(workspace):
            raise ConfigError(
                "sciencepal_workspace_violation",
                "input path escapes SCIENCEPAL_WORKSPACE",
            )
        if not candidate.is_file():
            raise ConfigError("sciencepal_input_missing", f"input file not found: {candidate.name}")
        return candidate
