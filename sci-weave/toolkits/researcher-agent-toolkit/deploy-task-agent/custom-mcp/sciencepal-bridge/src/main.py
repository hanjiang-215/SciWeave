"""stdio MCP surface for the SciencePal bridge.

Tools are intentionally small and JSON-string based so any MCP client can call
them without generated schemas: start, status, collect, cancel, agents.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from sciencepal_bridge.client import SciencePalError
from sciencepal_bridge.config import BridgeConfig, ConfigError
from sciencepal_bridge.service import SciencePalService

server = MCPServer(
    name="sciencepal-bridge",
    description="Delegate a research execution to SciencePal and collect its artifacts.",
    version="0.1.0",
)

_service: SciencePalService | None = None


def _get_service() -> SciencePalService:
    global _service
    if _service is None:
        try:
            _service = SciencePalService(BridgeConfig.from_env())
        except ConfigError as error:
            raise SciencePalError(error.code, str(error)) from None
    return _service


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error(code: str, message: str) -> str:
    return json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False)


def _guard(action) -> str:
    try:
        return _ok(action())
    except SciencePalError as error:
        return _error(error.code, error.message)
    except Exception:
        return _error("sciencepal_internal", "unexpected bridge error")


@server.tool(
    description=(
        "Start one SciencePal agent run. Returns run_id and thread_id immediately; "
        "use sciencepal_status to follow it and sciencepal_collect to fetch artifacts."
    )
)
def sciencepal_start(
    instruction: str,
    idempotency_key: str,
    execution_id: str = "",
    files_json: str = "",
    agent_id: str = "",
    agent_select_type: str = "manual",
    web_search: bool = True,
    model_name: str = "",
) -> str:
    def action() -> dict[str, Any]:
        try:
            files = json.loads(files_json) if files_json.strip() else []
        except json.JSONDecodeError:
            raise SciencePalError("invalid_arguments", "files_json must be a JSON array") from None
        if not isinstance(files, list):
            raise SciencePalError("invalid_arguments", "files_json must be a JSON array")
        return _get_service().start(
            instruction=instruction,
            idempotency_key=idempotency_key,
            execution_id=execution_id,
            files=files,
            agent_id=agent_id,
            agent_select_type=agent_select_type,
            web_search=web_search,
            model_name=model_name,
        )

    return _guard(action)


@server.tool(description="Read one SciencePal run status from the SDK API.")
def sciencepal_status(run_id: str) -> str:
    return _guard(lambda: _get_service().status(run_id))


@server.tool(
    description=(
        "Download all sandbox artifacts for a completed run into the workspace, "
        "verify sha256 and write a manifest. Optional names_json filters basenames."
    )
)
def sciencepal_collect(run_id: str, names_json: str = "") -> str:
    def action() -> dict[str, Any]:
        try:
            names = json.loads(names_json) if names_json.strip() else []
        except json.JSONDecodeError:
            raise SciencePalError("invalid_arguments", "names_json must be a JSON array") from None
        if not isinstance(names, list):
            raise SciencePalError("invalid_arguments", "names_json must be a JSON array")
        return _get_service().collect(run_id, names=[str(name) for name in names])

    return _guard(action)


@server.tool(description="Stop a queued or running SciencePal run. Idempotent for terminal runs.")
def sciencepal_cancel(run_id: str) -> str:
    return _guard(lambda: _get_service().cancel(run_id))


@server.tool(description="List SciencePal agents visible to the configured access token.")
def sciencepal_agents() -> str:
    return _guard(lambda: _get_service().list_agents())


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
