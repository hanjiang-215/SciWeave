"""stdio MCP surface for the SciencePal bridge.

Tools are intentionally small and JSON-string based so any MCP client can call
them without generated schemas: start, status, collect, cancel, agents, report.
"""

from __future__ import annotations

import argparse
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
def sciencepal_collect(run_id: str, names_json: str = "", roots_json: str = "") -> str:
    def action() -> dict[str, Any]:
        try:
            names = json.loads(names_json) if names_json.strip() else []
            roots = json.loads(roots_json) if roots_json.strip() else []
        except json.JSONDecodeError:
            raise SciencePalError("invalid_arguments", "names_json/roots_json must be JSON arrays") from None
        if not isinstance(names, list) or not isinstance(roots, list):
            raise SciencePalError("invalid_arguments", "names_json/roots_json must be JSON arrays")
        return _get_service().collect(
            run_id,
            names=[str(name) for name in names],
            roots=[str(root) for root in roots] or None,
        )

    return _guard(action)


@server.tool(description="Stop a queued or running SciencePal run. Idempotent for terminal runs.")
def sciencepal_cancel(run_id: str) -> str:
    return _guard(lambda: _get_service().cancel(run_id))


@server.tool(description="List SciencePal agents visible to the configured access token.")
def sciencepal_agents() -> str:
    return _guard(lambda: _get_service().list_agents())


@server.tool(
    description=(
        "Build the ExecutionReport for one run from the local ledger and collected "
        "artifacts. With write_draft=true it also opens a mapping_change draft in the "
        "central draft buffer and returns draft_id plus audit correlation ids. It never "
        "writes the formal Research Mapping, never submits a candidate and never formalizes."
    )
)
def sciencepal_report(
    run_id: str,
    task_node_id: str,
    execution_id: str = "",
    summary: str = "",
    acceptance_json: str = "",
    findings_json: str = "",
    limitations_json: str = "",
    route_change_json: str = "",
    write_draft: bool = False,
    idempotency_key: str = "",
) -> str:
    def action() -> dict[str, Any]:
        def _list(raw: str, label: str) -> list[Any]:
            if not raw.strip():
                return []
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                raise SciencePalError("invalid_arguments", f"{label} must be a JSON array") from None
            if not isinstance(value, list):
                raise SciencePalError("invalid_arguments", f"{label} must be a JSON array")
            return value

        try:
            route_change = json.loads(route_change_json) if route_change_json.strip() else None
        except json.JSONDecodeError:
            raise SciencePalError("invalid_arguments", "route_change_json must be a JSON object") from None
        if route_change is not None and not isinstance(route_change, dict):
            raise SciencePalError("invalid_arguments", "route_change_json must be a JSON object")

        return _get_service().report(
            run_id,
            task_node_id=task_node_id,
            execution_id=execution_id,
            summary=summary,
            acceptance=_list(acceptance_json, "acceptance_json"),
            findings=_list(findings_json, "findings_json"),
            limitations=_list(limitations_json, "limitations_json"),
            route_change=route_change,
            write_draft=write_draft,
            idempotency_key=idempotency_key,
        )

    return _guard(action)


def main() -> None:
    parser = argparse.ArgumentParser(description="SciencePal bridge MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()
    if args.transport == "http":
        # Local harnesses only: the bridge has no remote auth layer. Keep the
        # bind address on loopback unless a reverse proxy adds authentication.
        server.run("streamable-http", host=args.host, port=args.port)
    else:
        server.run()


if __name__ == "__main__":
    main()
