from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

SOURCE_COLLECTIONS = (
    "projects",
    "tasks",
    "wikiDocuments",
    "wikiCandidates",
    "executions",
    "services",
    "events",
)


@dataclass(frozen=True)
class SourceSpec:
    id: str
    label: str
    url: str | None
    collections: tuple[str, ...]
    bearer_token: str | None = None


class SourceUnavailable(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def fetch_json(source: SourceSpec, *, timeout_seconds: float, max_payload_bytes: int) -> Mapping[str, object]:
    if not source.url:
        raise SourceUnavailable("source_not_configured")
    request_headers = {"Accept": "application/json"}
    if source.bearer_token:
        request_headers["Authorization"] = f"Bearer {source.bearer_token}"
    request = Request(source.url, method="GET", headers=request_headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise SourceUnavailable("source_unavailable")
            content_type = response.headers.get_content_type()
            if content_type != "application/json" and not content_type.endswith("+json"):
                raise SourceUnavailable("source_invalid_response")
            raw = response.read(max_payload_bytes + 1)
            if len(raw) > max_payload_bytes:
                raise SourceUnavailable("source_invalid_response")
    except HTTPError:
        raise SourceUnavailable("source_unavailable") from None
    except (TimeoutError, URLError):
        raise SourceUnavailable("source_timeout") from None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SourceUnavailable("source_invalid_response") from None
    if not isinstance(value, dict):
        raise SourceUnavailable("source_invalid_response")
    return value
