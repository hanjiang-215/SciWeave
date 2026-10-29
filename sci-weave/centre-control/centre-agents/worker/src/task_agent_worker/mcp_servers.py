"""Turn the Centre Agent's MCP cards into fast-agent's `mcp.servers` block (ai4-349h).

The cards in ``libs/mcp-libs/*/mcp.json`` describe a server in the kit's own
vocabulary; fast-agent has a different one. Until this existed, the Centre
Worker's generated ``fast-agent.yaml`` carried only ``compaction`` and
``session_history``, so every prereview ran with **no MCP tools at all** — the
cards were documentation and the model could not read a candidate, let alone
append a verdict.

Three translations, and the differences are not cosmetic:

| card | fast-agent | note |
| --- | --- | --- |
| ``transport: streamable-http`` | ``transport: http`` | fast-agent spells it ``http``; its literal type is ``stdio`` / ``sse`` / ``http`` |
| ``endpoint.url_env`` | ``url`` | the card names the variable, the runtime needs the value |
| ``startup.project_dir_env`` | ``cwd`` | likewise |

**A missing variable is an error, not a skip.** A server silently dropped from
the config is an agent that quietly has fewer tools than its definition says,
and the first symptom is a model improvising around a tool it should have had.
Everything here names the variable *and* the card, because "MCP server
unavailable" with no name is a two-hour puzzle.

Only the servers an agent declares are emitted. That is the whole point of
``allowed_mcp_resources``: the agent that checks branch facts must not be
handed ``append_prereview_log``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

#: Kit transport name -> fast-agent transport name.
_TRANSPORTS = {"streamable-http": "http", "stdio": "stdio", "sse": "sse"}


class MCPServerConfigError(ValueError):
    """An MCP card cannot be turned into a fast-agent server entry."""

    def __init__(self, code: str, server: str, detail: str) -> None:
        self.code = code
        self.server = server
        self.detail = detail
        super().__init__(f"[{code}] {server}: {detail}")


@dataclass(frozen=True)
class MCPCard:
    """One card as read from disk: name, transport, the tool names, and the raw JSON.

    The card's ``environment`` list is deliberately *not* lifted onto this object.
    It names the variables a server needs, but the renderer emits only ``transport``
    and ``url``, so nothing here reads it and a field nobody reads is a field that
    drifts. The token half of that list is the live issue in ``ai4-sue2``; whatever
    consumes it will read ``document["environment"]`` and lift it then.
    """

    name: str
    transport: str
    tools: tuple[str, ...]
    document: Mapping[str, Any]


@dataclass(frozen=True)
class ServerSpec:
    name: str
    transport: str
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: str | None = None
    #: Bearer token for a remote (http) MCP server, taken from the token variable
    #: the card declares in ``environment``. fast-agent turns this into an
    #: ``Authorization: Bearer <token>`` header. Without it a bearer-only server
    #: (ours all are) is contacted unauthenticated, fast-agent then attempts OAuth
    #: dynamic client registration, the server 404s, and the worker dies on start
    #: (ai4-sue2).
    access_token: str | None = None


def load_cards(libs: str | Path) -> dict[str, MCPCard]:
    """Every ``<dir>/mcp.json`` under the cards root, keyed by declared name."""
    root = Path(libs)
    if not root.is_dir():
        raise MCPServerConfigError(
            "cards_missing", str(root), "MCP card directory does not exist"
        )
    cards: dict[str, MCPCard] = {}
    for path in sorted(root.glob("*/mcp.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MCPServerConfigError("card_invalid", path.parent.name, f"{path}: {error}") from error
        if not isinstance(document, Mapping):
            raise MCPServerConfigError("card_invalid", path.parent.name, f"{path} must be a JSON object")
        name = document.get("name")
        if not isinstance(name, str) or not name:
            raise MCPServerConfigError("card_invalid", path.parent.name, f"{path} declares no name")
        if name != path.parent.name:
            raise MCPServerConfigError(
                "card_name_mismatch", name, f"{path} is in {path.parent.name}/ but declares {name!r}"
            )
        if name in cards:
            raise MCPServerConfigError("card_duplicate", name, "declared by more than one card")
        raw_tools = document.get("tools") or []
        tools = tuple(
            str(tool["name"])
            for tool in raw_tools
            if isinstance(tool, Mapping) and isinstance(tool.get("name"), str)
        )
        cards[name] = MCPCard(
            name=name,
            transport=str(document.get("transport", "streamable-http")),
            tools=tools,
            document=document,
        )
    if not cards:
        raise MCPServerConfigError("cards_missing", str(root), "no */mcp.json found")
    return cards


def _env(environ: Mapping[str, str], name: str, server: str) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise MCPServerConfigError(
            "missing_environment",
            server,
            f"{name} is not set; the Centre Agent cannot start this server without it",
        )
    return value


def server_spec(card: MCPCard, environ: Mapping[str, str]) -> ServerSpec:
    """One card -> one server spec. Raises when something it needs is absent."""
    if card.transport not in _TRANSPORTS:
        raise MCPServerConfigError(
            "unsupported_transport",
            card.name,
            f"{card.transport!r} is not one of {', '.join(sorted(_TRANSPORTS))}",
        )
    transport = _TRANSPORTS[card.transport]
    if transport == "stdio":
        startup = card.document.get("startup") or {}
        executable = str(startup.get("executable") or "").strip()
        if not executable:
            raise MCPServerConfigError("invalid_startup", card.name, "startup.executable is required")
        # ``project_dir_env`` names the directory the server's project lives in and
        # ``args`` are relative to it, so a missing cwd turns into a confusing
        # "file not found" much later.
        cwd_variable = str(startup.get("project_dir_env") or "").strip()
        cwd = _env(environ, cwd_variable, card.name) if cwd_variable else None
        return ServerSpec(
            name=card.name,
            transport=transport,
            command=executable,
            args=tuple(str(part) for part in startup.get("args") or ()),
            cwd=cwd,
        )
    endpoint = card.document.get("endpoint") or {}
    url_variable = str(endpoint.get("url_env") or "").strip()
    if not url_variable:
        raise MCPServerConfigError(
            "invalid_endpoint",
            card.name,
            "endpoint.url_env is required for a remote server; there is no default URL to fall back on",
        )
    url = _env(environ, url_variable, card.name)
    token_variable = _token_variable(card, url_variable)
    access_token = None
    if token_variable:
        raw = (environ.get(token_variable) or "").strip()
        if not raw:
            raise MCPServerConfigError(
                "missing_environment",
                card.name,
                f"{token_variable} is not set; the Centre Agent cannot authenticate to this server without it",
            )
        access_token = raw
    return ServerSpec(
        name=card.name, transport=transport, url=url, access_token=access_token
    )


def _token_variable(card: MCPCard, url_variable: str) -> str | None:
    """The token variable a remote card declares for its server.

    Preference order: an explicit ``environment`` entry named exactly
    ``<url_variable minus _URL>_TOKEN`` (e.g. ``RESEARCH_MAPPING_MCP_URL`` ->
    ``RESEARCH_MAPPING_MCP_TOKEN``), else the single ``environment`` entry ending
    in ``_TOKEN`` that is not the url variable. A card that declares no token
    variable is left unauthenticated on purpose (public server).
    """
    environment = card.document.get("environment") or []
    if not isinstance(environment, (list, tuple)):
        return None
    names = [str(item) for item in environment if isinstance(item, str)]
    if url_variable.endswith("_URL"):
        guessed = url_variable[: -len("_URL")] + "_TOKEN"
        if guessed in names:
            return guessed
    token_names = [name for name in names if name.endswith("_TOKEN") and name != url_variable]
    if len(token_names) == 1:
        return token_names[0]
    return None


def fast_agent_servers(
    names: tuple[str, ...] | list[str],
    cards: Mapping[str, MCPCard],
    environ: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """The ``mcp.servers`` mapping for one agent's declared resources."""
    servers: dict[str, dict[str, Any]] = {}
    for name in names:
        card = cards.get(name)
        if card is None:
            known = ", ".join(sorted(cards)) or "(none)"
            raise MCPServerConfigError(
                "unknown_server", name, f"no card declares this name; known cards: {known}"
            )
        spec = server_spec(card, environ)
        entry: dict[str, Any] = {"transport": spec.transport}
        if spec.url is not None:
            entry["url"] = spec.url
        if spec.access_token is not None:
            entry["access_token"] = spec.access_token
        if spec.command is not None:
            entry["command"] = spec.command
            entry["args"] = list(spec.args)
        if spec.cwd is not None:
            entry["cwd"] = spec.cwd
        servers[name] = entry
    return servers


def render_fast_agent_config(servers: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    """The ``fast-agent.yaml`` body: our two settings, then the MCP block.

    Emitted as text rather than via ``yaml.safe_dump`` so the file stays readable
    and diffable. It is a generated artifact an operator opens while debugging,
    and a dump with anchors and quoting noise is worse than useless there.
    """
    lines = ["compaction:", "  auto: false", "session_history: true"]
    if not servers:
        return "\n".join(lines) + "\n"
    lines += ["mcp:", "  servers:"]
    for name in sorted(servers):
        entry = servers[name]
        lines.append(f"    {name}:")
        lines.append(f"      transport: {entry['transport']}")
        for key in ("url", "command", "cwd", "access_token"):
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
