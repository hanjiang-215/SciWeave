from __future__ import annotations

import json
import os
from dataclasses import dataclass
from collections.abc import Mapping
from . import BufferError


@dataclass(frozen=True)
class BufferConfig:
    terminusdb_url: str
    terminusdb_database: str
    terminusdb_username: str | None
    terminusdb_password: str | None
    terminusdb_token: str | None
    request_timeout_seconds: float
    reviewers: dict[str, frozenset[str]]
    mcp_host: str | None = None
    mcp_port: int | None = None
    tokens: dict[str, str] | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "BufferConfig":
        env = os.environ if environment is None else environment
        required = ("SCIWEAVE_BUFFER_TERMINUSDB_URL", "SCIWEAVE_BUFFER_TERMINUSDB_DATABASE")
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise BufferError("configuration_missing", "missing required environment variables: " + ", ".join(missing))
        token = env.get("SCIWEAVE_BUFFER_TERMINUSDB_TOKEN") or None
        username = env.get("SCIWEAVE_BUFFER_TERMINUSDB_USERNAME") or None
        password = env.get("SCIWEAVE_BUFFER_TERMINUSDB_PASSWORD") or None
        if token and (username or password):
            raise BufferError("configuration_invalid", "configure either a token or basic credentials, not both")
        if bool(username) != bool(password):
            raise BufferError("configuration_invalid", "configure both username and password for basic authentication")
        try:
            timeout = float(env.get("SCIWEAVE_BUFFER_REQUEST_TIMEOUT_SECONDS", "10"))
            if timeout <= 0:
                raise ValueError
        except ValueError:
            raise BufferError("configuration_invalid", "request timeout must be a positive number") from None
        reviewers: dict[str, frozenset[str]] = {"mapping": frozenset(), "wiki": frozenset()}
        raw = env.get("SCIWEAVE_BUFFER_REVIEWERS_JSON")
        if raw:
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                raise BufferError("configuration_invalid", "reviewers configuration must be valid JSON") from None
            if not isinstance(decoded, dict) or set(decoded) - {"mapping", "wiki"}:
                raise BufferError("configuration_invalid", "reviewers configuration may contain only mapping and wiki namespaces")
            for namespace, ids in decoded.items():
                if not isinstance(ids, list) or not all(isinstance(item, str) and item.strip() for item in ids):
                    raise BufferError("configuration_invalid", f"reviewers for {namespace} must be a list of non-empty IDs")
                reviewers[namespace] = frozenset(ids)
        mcp_host = env.get("SCIWEAVE_BUFFER_MCP_HOST") or None
        mcp_port = env.get("SCIWEAVE_BUFFER_MCP_PORT")
        if (mcp_host is None) != (mcp_port is None):
            raise BufferError("configuration_invalid", "configure both SCIWEAVE_BUFFER_MCP_HOST and SCIWEAVE_BUFFER_MCP_PORT for the MCP endpoint")
        tokens: dict[str, str] = {}
        raw_tokens = env.get("SCIWEAVE_BUFFER_MCP_TOKENS_JSON")
        if raw_tokens:
            try:
                decoded_tokens = json.loads(raw_tokens)
            except json.JSONDecodeError:
                raise BufferError("configuration_invalid", "MCP tokens configuration must be valid JSON") from None
            if not isinstance(decoded_tokens, dict) or not all(
                isinstance(token, str) and token.strip() and isinstance(actor, str) and actor.strip()
                for token, actor in decoded_tokens.items()
            ):
                raise BufferError("configuration_invalid", "MCP tokens must map non-empty token strings to non-empty actor IDs")
            tokens = {str(token): str(actor) for token, actor in decoded_tokens.items()}
        return cls(env[required[0]].rstrip("/"), env[required[1]], username, password, token, timeout, reviewers,
                   mcp_host=mcp_host, mcp_port=int(mcp_port) if mcp_port is not None else None, tokens=tokens or None)
