from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import ConfigError

_REQUIRED_VARIABLES = (
    "SCIWEAVE_MAPPING_SQLITE_PATH",
    "SCIWEAVE_MAPPING_DOMAIN_ID",
    "SCIWEAVE_MAPPING_TERMINUSDB_URL",
    "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
)

_CAPABILITY_ORDER = (
    "read", "candidate_submit", "candidate_review", "formalize",
    "centre", "prereview_log", "merged_candidate",
)


@dataclass(frozen=True)
class MappingConfig:
    sqlite_path: str
    mapping_domain_id: str
    terminusdb_url: str
    terminusdb_database: str
    terminusdb_store: str
    terminusdb_token: str | None = None
    terminusdb_username: str | None = None
    terminusdb_password: str | None = None
    mcp_host: str | None = None
    mcp_port: int | None = None
    mcp_tokens: dict[str, str] | None = None
    caller_capabilities: dict[str, frozenset[str]] | None = None
    audit_sqlite_path: str | None = None
    prereview_rules_dir: str | None = None
    governance_kafka_bootstrap: str | None = None

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "MappingConfig":
        env = os.environ if environment is None else environment
        missing = [name for name in _REQUIRED_VARIABLES if not env.get(name)]
        if missing:
            raise ConfigError(
                "missing required environment variables: " + ", ".join(missing)
            )
        token = env.get("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN") or None
        mcp_host = env.get("SCIWEAVE_MAPPING_MCP_HOST") or None
        mcp_port_text = env.get("SCIWEAVE_MAPPING_MCP_PORT")
        if (mcp_host is None) != (mcp_port_text is None):
            raise ConfigError(
                "configure both SCIWEAVE_MAPPING_MCP_HOST and SCIWEAVE_MAPPING_MCP_PORT for the management MCP endpoint"
            )
        mcp_port = None
        if mcp_port_text is not None:
            try:
                mcp_port = int(mcp_port_text)
            except ValueError:
                raise ConfigError("SCIWEAVE_MAPPING_MCP_PORT must be an integer") from None
        mcp_tokens = _parse_token_map(env.get("SCIWEAVE_MAPPING_MCP_TOKENS_JSON"))
        caller_capabilities = _parse_capabilities(env.get("SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON"))
        audit_sqlite_path = env.get("SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH") or None
        prereview_rules_dir = env.get("SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR") or None
        governance_kafka_bootstrap = env.get("SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP") or None
        return cls(
            sqlite_path=env["SCIWEAVE_MAPPING_SQLITE_PATH"],
            mapping_domain_id=env["SCIWEAVE_MAPPING_DOMAIN_ID"],
            terminusdb_url=env["SCIWEAVE_MAPPING_TERMINUSDB_URL"],
            terminusdb_database=env["SCIWEAVE_MAPPING_TERMINUSDB_DATABASE"],
            terminusdb_store=env["SCIWEAVE_MAPPING_TERMINUSDB_STORE"],
            terminusdb_token=token,
            terminusdb_username=env.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME") or None,
            terminusdb_password=env.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD") or None,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
            mcp_tokens=mcp_tokens or None,
            caller_capabilities=caller_capabilities or None,
            audit_sqlite_path=audit_sqlite_path,
            prereview_rules_dir=prereview_rules_dir,
        )


def _parse_token_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        raise ConfigError("SCIWEAVE_MAPPING_MCP_TOKENS_JSON must be valid JSON") from None
    if not isinstance(decoded, dict) or not all(
        isinstance(value, str) and value.strip()
        for value in decoded.values()
    ):
        raise ConfigError("SCIWEAVE_MAPPING_MCP_TOKENS_JSON must map tokens to non-empty actor IDs")
    return {str(key): str(value) for key, value in decoded.items() if key}


def _parse_capabilities(raw: str | None) -> dict[str, frozenset[str]]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        raise ConfigError("SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON must be valid JSON") from None
    if not isinstance(decoded, dict):
        raise ConfigError("SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON must be an object")
    result: dict[str, frozenset[str]] = {}
    for actor, capabilities in decoded.items():
        if not isinstance(capabilities, list) or not capabilities:
            raise ConfigError(f"capabilities for {actor} must be a non-empty list")
        unknown = set(capabilities) - set(_CAPABILITY_ORDER)
        if unknown:
            raise ConfigError(f"unknown capabilities for {actor}: {sorted(unknown)}")
        result[str(actor)] = frozenset(capabilities)
    return result
