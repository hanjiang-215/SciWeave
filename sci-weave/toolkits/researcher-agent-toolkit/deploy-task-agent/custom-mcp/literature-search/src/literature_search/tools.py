"""The two tools the card exposes, independent of the MCP transport.

Keeping this layer free of MCP imports means the tests exercise the exact code
the server runs without starting a stdio loop.
"""

from __future__ import annotations

import json
from typing import Any

from . import arxiv, crossref
from .config import LiteratureConfig
from .errors import LiteratureError, invalid_arguments, unsupported_source

SOURCES = ("arxiv", "crossref")


def _resolve_source(source: str) -> str:
    text = (source or "").strip().lower()
    if not text:
        return "arxiv"
    if text not in SOURCES:
        raise unsupported_source(source)
    return text


def search(
    query: str,
    source: str,
    limit: int,
    config: LiteratureConfig,
    *,
    transport: Any = None,
) -> list[dict[str, Any]]:
    chosen = _resolve_source(source)
    if chosen == "crossref":
        return crossref.search(query, limit, config, transport=transport)
    return arxiv.search(query, limit, config, transport=transport)


def get_abstract(
    identifier: str,
    source: str,
    config: LiteratureConfig,
    *,
    transport: Any = None,
) -> dict[str, Any]:
    """Fetch one record; ``source`` empty means "infer it from the id's shape"."""
    text = (identifier or "").strip()
    if not text:
        raise invalid_arguments("id must not be empty")
    chosen = _resolve_source(source) if (source or "").strip() else arxiv.id_kind(text)
    if chosen == "crossref":
        return crossref.get_abstract(text, config, transport=transport)
    return arxiv.get_abstract(text, config, transport=transport)


def call(tool: str, arguments: dict[str, Any], config: LiteratureConfig, *, transport: Any = None) -> str:
    """Dispatch one tool call and always return JSON, never raise to the client."""
    try:
        if tool == "search":
            payload: Any = search(
                str(arguments.get("query", "")),
                str(arguments.get("source", "")),
                int(arguments.get("limit", 5)),
                config,
                transport=transport,
            )
        elif tool == "get_abstract":
            payload = get_abstract(
                str(arguments.get("id", "")),
                str(arguments.get("source", "")),
                config,
                transport=transport,
            )
        else:
            raise LiteratureError("unknown_tool", f"{tool} is not a literature-search tool")
    except LiteratureError as error:
        return json.dumps({"error": {"code": error.code, "message": error.message}}, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(
            {"error": {"code": "invalid_arguments", "message": "arguments must be strings and integers"}},
            ensure_ascii=False,
        )
    except Exception:
        # An unexpected bug must not tear down the stdio loop mid-session: the
        # client would see a broken pipe instead of an actionable error. The
        # code is deliberately generic so it never looks like a real diagnosis.
        return json.dumps(
            {"error": {"code": "literature_internal", "message": "internal error while handling the call"}},
            ensure_ascii=False,
        )
    return json.dumps(payload, ensure_ascii=False)
