"""Gateway MCP console-script entry point."""

from __future__ import annotations

import logging
import os

from task_agent_worker.config import WorkerSettings

from .app import create_app, serve

logger = logging.getLogger(__name__)

# ai4-c61f: the passthrough runtime writes a stub history and reports
# ``completed``, so it must be an explicit choice rather than the silent
# fallback when no API key is configured.
PASSTHROUGH_SWITCH = "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME"


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} must be configured through the environment")
    return value


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = create_app(
        required_environment("SCIWEAVE_GATEWAY_DB"),
        required_environment("SCIWEAVE_GATEWAY_TOKEN"),
        required_environment("SCIWEAVE_GATEWAY_CALLER_ID"),
    )
    try:
        settings = WorkerSettings.from_environment()
        settings.validate_runtime(require_api_key=False)
    except ValueError as error:
        logger.error("worker runtime is misconfigured: %s", error)
        app.mark_runtime_misconfigured(f"worker_settings_invalid: {error}")
    else:
        if settings.api_key:
            app.enable_fast_agent_deepseek_runtime(settings)
        elif os.environ.get(PASSTHROUGH_SWITCH) == "1":
            logger.warning(
                "fast-agent passthrough runtime enabled: executions write a stub "
                "history instead of calling a model (%s=1)",
                PASSTHROUGH_SWITCH,
            )
            app.enable_fast_agent_passthrough_runtime(
                str(settings.home), settings.connection_scope, settings.session_dir
            )
        else:
            logger.error(
                "no Worker runtime: the DeepSeek API key is unset and the "
                "passthrough runtime is not enabled (%s=1)",
                PASSTHROUGH_SWITCH,
            )
            app.mark_runtime_misconfigured("api_key_missing")
    serve(
        app,
        required_environment("SCIWEAVE_GATEWAY_HOST"),
        int(required_environment("SCIWEAVE_GATEWAY_PORT")),
    )
