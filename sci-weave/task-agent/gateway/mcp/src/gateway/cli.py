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
    serve(
        create_app(
            required_environment("SCIWEAVE_GATEWAY_DB"),
            required_environment("SCIWEAVE_GATEWAY_TOKEN"),
            required_environment("SCIWEAVE_GATEWAY_CALLER_ID"),
        ),
        required_environment("SCIWEAVE_GATEWAY_HOST"),
        int(required_environment("SCIWEAVE_GATEWAY_PORT")),
    )
