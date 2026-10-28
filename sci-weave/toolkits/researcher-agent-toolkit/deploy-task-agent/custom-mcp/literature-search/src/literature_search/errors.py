"""Stable error codes for the literature MCP.

Every failure that reaches an agent goes through :class:`LiteratureError`, so
the tools never leak a bare httpx or XML exception. The codes are part of the
card contract in ``libs/mcp-libs/literature-search/mcp.json``.
"""

from __future__ import annotations


class LiteratureError(ValueError):
    """A failure with a code an agent can branch on."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def invalid_arguments(message: str) -> LiteratureError:
    return LiteratureError("invalid_arguments", message)


def unsupported_source(source: str) -> LiteratureError:
    return LiteratureError(
        "unsupported_source", f"source must be arxiv or crossref, got {source!r}"
    )
