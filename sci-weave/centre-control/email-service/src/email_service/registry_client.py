from __future__ import annotations

import inspect
import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .ports import EmailServiceError


class RegistryRecipientResolver:
    """Resolve notification principals through the Registry read-only MCP tool."""

    def __init__(self, url: str, token: str, timeout_seconds: float) -> None:
        self.url = url
        self.token = token
        self.timeout_seconds = timeout_seconds

    async def resolve(self, principal_id: str) -> str:
        headers = {"Authorization": f"Bearer {self.token}"}
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(headers=headers, timeout=timeout) as http:
                async with streamable_http_client(self.url, http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            "get_principal_contact", {"principal_id": principal_id}
                        )
        except httpx.HTTPStatusError as exc:
            raise EmailServiceError(_transport_error_code(exc)) from exc
        except (httpx.HTTPError, TimeoutError, OSError) as exc:
            raise EmailServiceError("registry_unavailable") from exc
        except Exception as exc:
            raise EmailServiceError(_transport_error_code(exc)) from exc

        payload = _result_payload(result)
        if getattr(result, "isError", False):
            raise EmailServiceError(_error_code(payload) if isinstance(payload, dict) else _error_code_from_text(_first_text(result)))
        if not isinstance(payload, dict):
            raise EmailServiceError("registry_unavailable")
        error = payload.get("error")
        if isinstance(error, dict):
            raise EmailServiceError(_error_code(payload))
        contact_email = payload.get("contact_email")
        status = payload.get("status")
        if payload.get("principal_id") != principal_id or status != "active":
            raise EmailServiceError("registry_unavailable")
        if not isinstance(contact_email, str) or not contact_email:
            raise EmailServiceError("registry_unavailable")
        return contact_email


def _result_payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        return structured
    for item in getattr(result, "content", ()):
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def _first_text(result: Any) -> str | None:
    for item in getattr(result, "content", ()):
        text = getattr(item, "text", None)
        if isinstance(text, str):
            return text
    return None


def _error_code(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return _stable_error(error["code"])
        if isinstance(payload.get("code"), str):
            return _stable_error(payload["code"])
    return "registry_unavailable"


def _error_code_from_text(text: str | None) -> str:
    # ai4-dp9t: the real Registry returns a plain-text error, e.g.
    # "Error executing tool get_principal_contact: contact_missing", not a JSON
    # payload. Take the suffix after the last ": " and adopt it only when it is
    # a known code; anything else (unknown suffix, multi-line pydantic
    # validation text, missing/empty content) falls back to registry_unavailable
    # without raising.
    if not isinstance(text, str) or ": " not in text:
        return "registry_unavailable"
    suffix = text.rsplit(": ", 1)[-1].strip()
    return _stable_error(suffix)


def _stable_error(code: str) -> str:
    if code in {"principal_not_found", "contact_missing", "contact_disabled", "address_mismatch"}:
        return code
    if code in {"unauthorized", "denied", "forbidden", "permission_denied"}:
        return "registry_denied"
    return "registry_unavailable"


def _transport_error_code(exc: Exception) -> str:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in {401, 403}:
        return "registry_denied"
    return "registry_unavailable"


async def resolve_recipient(resolver: Any, principal_id: str) -> str:
    """Support the async resolver contract while easing migration of test fakes."""
    result = resolver.resolve(principal_id)
    if inspect.isawaitable(result):
        return await result
    return result
