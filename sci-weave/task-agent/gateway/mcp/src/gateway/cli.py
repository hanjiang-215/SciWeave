"""Gateway MCP console-script entry point."""

from __future__ import annotations

import os

from .app import create_app, serve


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} must be configured through the environment")
    return value


def main() -> None:
    app = create_app(
        required_environment("SCIWEAVE_GATEWAY_DB"),
        required_environment("SCIWEAVE_GATEWAY_TOKEN"),
        required_environment("SCIWEAVE_GATEWAY_CALLER_ID"),
    )
    worker_home = os.environ.get("SCIWEAVE_WORKER_HOME")
    session_dir = os.environ.get("SCIWEAVE_WORKER_SESSION_DIR", "sessions")
    if worker_home:
        settings = WorkerSettings.from_environment()
        if settings.api_key:
            app.enable_fast_agent_deepseek_runtime(settings)
        else:
            app.enable_fast_agent_passthrough_runtime(worker_home, session_dir)
    serve(
        app,
        required_environment("SCIWEAVE_GATEWAY_HOST"),
        int(required_environment("SCIWEAVE_GATEWAY_PORT")),
    )
