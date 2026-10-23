from __future__ import annotations

from dataclasses import dataclass
import math
from urllib.parse import urlparse
import os
from typing import Mapping

from .sources import SourceSpec


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class DashboardConfig:
    host: str
    port: int
    timeout_seconds: float
    max_payload_bytes: int
    cors_origin: str | None
    source_specs: tuple[SourceSpec, ...]

    @property
    def source_urls(self) -> dict[str, str | None]:
        return {source.id: source.url for source in self.source_specs}

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "DashboardConfig":
        values = os.environ if env is None else env
        host = values.get("SCIWEAVE_DASHBOARD_HOST", "").strip()
        if not host:
            raise ConfigurationError("SCIWEAVE_DASHBOARD_HOST is required")
        port = _integer(values.get("SCIWEAVE_DASHBOARD_PORT"), "SCIWEAVE_DASHBOARD_PORT", minimum=0, maximum=65535)
        timeout = _decimal(values.get("SCIWEAVE_DASHBOARD_SOURCE_TIMEOUT_SECONDS", "5"), "SCIWEAVE_DASHBOARD_SOURCE_TIMEOUT_SECONDS", minimum=0.1)
        max_payload_bytes = _integer(values.get("SCIWEAVE_DASHBOARD_SOURCE_MAX_BYTES", "1048576"), "SCIWEAVE_DASHBOARD_SOURCE_MAX_BYTES", minimum=1024, maximum=50_000_000)
        cors_origin = _origin(values.get("SCIWEAVE_DASHBOARD_CORS_ORIGIN", "").strip() or None)
        source_specs = (
            SourceSpec("mapping", "Research Mapping", _url(values.get("SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL"), "SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL"), ("projects", "tasks", "events"), values.get("SCIWEAVE_DASHBOARD_SOURCE_MAPPING_TOKEN") or None),
            SourceSpec("wiki", "LLM-Wiki", _url(values.get("SCIWEAVE_DASHBOARD_SOURCE_WIKI_URL"), "SCIWEAVE_DASHBOARD_SOURCE_WIKI_URL"), ("wikiDocuments", "wikiCandidates", "events"), values.get("SCIWEAVE_DASHBOARD_SOURCE_WIKI_TOKEN") or None),
            SourceSpec("gateway", "Gateway", _url(values.get("SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_URL"), "SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_URL"), ("executions", "services", "events"), values.get("SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_TOKEN") or None),
            SourceSpec("queue", "消息监听", _url(values.get("SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL"), "SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL"), ("services", "events"), values.get("SCIWEAVE_DASHBOARD_SOURCE_QUEUE_TOKEN") or None),
        )
        return cls(host=host, port=port, timeout_seconds=timeout, max_payload_bytes=max_payload_bytes, cors_origin=cors_origin, source_specs=source_specs)


def _integer(value: str | None, name: str, *, minimum: int, maximum: int) -> int:
    try:
        result = int(value or "")
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer") from None
    if result < minimum or result > maximum:
        raise ConfigurationError(f"{name} is outside the allowed range")
    return result


def _decimal(value: str, name: str, *, minimum: float) -> float:
    try:
        result = float(value)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number") from None
    if not math.isfinite(result) or result < minimum:
        raise ConfigurationError(f"{name} is outside the allowed range")
    return result


def _url(value: str | None, name: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        raise ConfigurationError(f"{name} must be a valid HTTP(S) URL") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ConfigurationError(f"{name} must be an HTTP(S) URL without credentials")
    return value


def _origin(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError:
        raise ConfigurationError("SCIWEAVE_DASHBOARD_CORS_ORIGIN must be a valid origin") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ConfigurationError("SCIWEAVE_DASHBOARD_CORS_ORIGIN must contain only an HTTP(S) origin")
    return f"{parsed.scheme}://{parsed.netloc}"
