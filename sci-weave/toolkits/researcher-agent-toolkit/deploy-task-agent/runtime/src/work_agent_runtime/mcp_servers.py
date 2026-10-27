"""Translate MCP cards into fast-agent's `mcp.servers` block (ai4-x0ay).

The cards in `libs/mcp-libs/*/mcp.json` describe a server in the kit's own
vocabulary; fast-agent has a different one. Until this existed, the generated
`fast-agent.yaml` carried only `compaction` and `session_history`, so every
agent ran with **no MCP tools at all** — the cards were documentation.

Three translations, and the differences are not cosmetic:

| card | fast-agent | note |
| --- | --- | --- |
| `transport: streamable-http` | `transport: http` | fast-agent spells it `http`; its literal type is `stdio`/`sse`/`http` |
| `endpoint.url_env` | `url` | the card names the variable, the runtime needs the value |
| `startup.project_dir_env` | `cwd` | likewise |

**A missing variable is an error, not a skip.** A server silently dropped from
the config is an agent that quietly has fewer tools than its definition says,
and the first symptom is a model improvising around a tool it should have had.
`MCPServerConfigError` names the variable and the server so the fix is obvious.

Only the servers an agent declares are emitted. That is the whole point of
`allowed_mcp_resources`: a reader agent must not be handed `create_draft`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

#: Kit transport name -> fast-agent transport name.
_TRANSPORTS = {"streamable-http": "http", "stdio": "stdio", "sse": "sse"}


class MCPServerConfigError(ValueError):
    """An MCP card cannot be turned into a fast-agent server entry."""

    def __init__(self, code: str, server: str, detail: str) -> None:
        self.code = code
        self.server = server
        super().__init__(f"[{code}] {server}: {detail}")


@dataclass(frozen=True)
class ServerSpec:
    name: str
    transport: str
    url: str | None
    command: str | None
    args: tuple[str, ...]
    cwd: str | None


def _env(environ: Mapping[str, str], name: str, server: str, *, required: bool) -> str:
    value = (environ.get(name) or "").strip()
    if not value and required:
        raise MCPServerConfigError(
            "missing_environment",
            server,
            f"{name} is not set; the kit cannot start this server without it",
        )
    return value


def server_spec(
    name: str, card: Mapping[str, Any], environ: Mapping[str, str] | None = None
) -> ServerSpec:
    """One card -> one server spec. Raises when something it needs is absent."""
    env = dict(os.environ) if environ is None else environ
    transport = str(card.get("transport", "streamable-http"))
    if transport not in _TRANSPORTS:
        raise MCPServerConfigError(
            "unsupported_transport", name, f"{transport!r} is not one of {', '.join(sorted(_TRANSPORTS))}"
        )
    fast_transport = _TRANSPORTS[transport]

    if fast_transport == "stdio":
        startup = card.get("startup") or {}
        executable = str(startup.get("executable") or "").strip()
        if not executable:
            raise MCPServerConfigError("invalid_startup", name, "startup.executable is required")
        # The card's `project_dir_env` names the directory the server's project
        # lives in; `args` are relative to it (`src/main.py`), so a cwd that
        # does not exist turns into a confusing "file not found" much later.
        cwd_variable = str(startup.get("project_dir_env") or "").strip()
        cwd = _env(env, cwd_variable, name, required=True) if cwd_variable else None
        return ServerSpec(
            name,
            fast_transport,
            None,
            executable,
            tuple(str(part) for part in startup.get("args") or ()),
            cwd,
        )

    endpoint = card.get("endpoint") or {}
    url_variable = str(endpoint.get("url_env") or "").strip()
    if not url_variable:
        raise MCPServerConfigError(
            "invalid_endpoint",
            name,
            "endpoint.url_env is required for a remote server; there is no default URL to fall back on",
        )
    return ServerSpec(name, fast_transport, _env(env, url_variable, name, required=True), None, (), None)


def fast_agent_servers(
    names: tuple[str, ...], catalog: Mapping[str, Any], environ: Mapping[str, str] | None = None
) -> dict[str, dict[str, Any]]:
    """The `mcp.servers` mapping for one agent's declared resources.

    ``catalog`` is `MCPRegistry.catalog()`: card metadata keyed by server name.
    An unknown name is an error here as a second line of defence — the config
    loader already rejects unknown resources against the same registry.
    """
    servers: dict[str, dict[str, Any]] = {}
    for name in names:
        card = catalog.get(name)
        if card is None:
            raise MCPServerConfigError("unknown_server", name, "not present in the MCP catalog")
        spec = server_spec(name, card, environ)
        entry: dict[str, Any] = {"transport": spec.transport}
        if spec.url is not None:
            entry["url"] = spec.url
        if spec.command is not None:
            entry["command"] = spec.command
            entry["args"] = list(spec.args)
        if spec.cwd is not None:
            entry["cwd"] = spec.cwd
        servers[name] = entry
    return servers


def render_fast_agent_config(
    servers: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """The `fast-agent.yaml` body: our two settings, then the MCP block.

    Emitted as text rather than via `yaml.safe_dump` to keep the file readable
    and diffable: this is a generated artifact a researcher may open while
    debugging, and a dump with anchors and quoting noise is worse than useless
    there.
    """
    lines = ["compaction:", "  auto: false", "session_history: true"]
    if not servers:
        return "\n".join(lines) + "\n"
    lines += ["mcp:", "  servers:"]
    for name in sorted(servers):
        entry = servers[name]
        lines.append(f"    {name}:")
        lines.append(f"      transport: {entry['transport']}")
        for key in ("url", "command", "cwd"):
            if entry.get(key):
                lines.append(f"      {key}: {_quote(str(entry[key]))}")
        if entry.get("args"):
            lines.append("      args:")
            lines += [f"        - {_quote(str(item))}" for item in entry["args"]]
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    """Quote only when a plain scalar would not survive a YAML round trip."""
    if value and not any(character in value for character in ":#{}[]&*!|>'\"%@`,") and value == value.strip():
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
