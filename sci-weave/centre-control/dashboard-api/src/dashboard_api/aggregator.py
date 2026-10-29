from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
import re
from time import monotonic
from typing import Callable, Mapping, Sequence

from .sources import SOURCE_COLLECTIONS, SourceSpec, SourceUnavailable

logger = logging.getLogger(__name__)

#: Overall budget for one snapshot. Each source has its own socket timeout, but
#: without a total deadline N slow sources add up and the HTTP client gives up
#: with a 5xx instead of getting a partial snapshot (ai4-onvr).
DEFAULT_DEADLINE_SECONDS = 10.0


class SnapshotValidationError(ValueError):
    pass


class DashboardAggregator:
    """Combine allow-listed read-only source fragments into one snapshot."""

    def __init__(
        self,
        sources: Sequence[SourceSpec],
        fetch_contribution: Callable[[SourceSpec], Mapping[str, object]],
        *,
        now: Callable[[], datetime] | None = None,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    ) -> None:
        self._sources = tuple(sources)
        self._fetch = fetch_contribution
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._deadline_seconds = max(float(deadline_seconds), 0.1)

    def get_snapshot(self) -> dict[str, object]:
        contributions: dict[str, tuple[dict[str, object], str | None]] = {}
        configured = [source for source in self._sources if source.url]
        if configured:
            deadline = monotonic() + self._deadline_seconds
            with ThreadPoolExecutor(max_workers=len(configured), thread_name_prefix="dashboard-source") as executor:
                futures = {source.id: executor.submit(self._fetch, source) for source in configured}
                for source in configured:
                    remaining = deadline - monotonic()
                    try:
                        if remaining <= 0:
                            raise FutureTimeoutError()
                        raw = futures[source.id].result(timeout=remaining)
                        contributions[source.id] = (self._normalize(source, raw), None)
                    except SnapshotValidationError:
                        contributions[source.id] = ({}, "source_invalid_response")
                    except SourceUnavailable as error:
                        contributions[source.id] = ({}, error.reason_code)
                    except FutureTimeoutError:
                        # Report the timed-out source as unavailable instead of
                        # letting the whole snapshot fail.
                        logger.warning("dashboard source %s exceeded the %.1fs snapshot deadline",
                                       source.id, self._deadline_seconds)
                        contributions[source.id] = ({}, "source_timeout")
                    except Exception:
                        logger.exception("dashboard source %s raised", source.id)
                        contributions[source.id] = ({}, "source_unavailable")

        arrays: dict[str, list[object]] = {collection: [] for collection in SOURCE_COLLECTIONS}
        source_results: list[dict[str, object]] = []
        partial = False
        for source in self._sources:
            normalized, error_code = contributions.get(source.id, ({}, "source_not_configured"))
            if error_code is not None:
                status = "unavailable"
                source_result: dict[str, object] = {
                    "id": source.id,
                    "label": source.label,
                    "status": status,
                    "error": _public_error(error_code),
                }
            else:
                status = str(normalized["sourceStatus"])
                source_result = {
                    "id": source.id,
                    "label": source.label,
                    "status": status,
                    "observedAt": normalized["observedAt"],
                }
                if "freshUntil" in normalized:
                    source_result["freshUntil"] = normalized["freshUntil"]
                if status != "fresh":
                    source_result["error"] = _public_error(f"source_{status}")
                if status != "unavailable":
                    for collection in source.collections:
                        arrays[collection].extend(normalized[collection])
            source_results.append(source_result)
            partial = partial or status != "fresh"

        return {
            "mode": "live",
            "observedAt": _format_time(self._now()),
            "sources": source_results,
            **arrays,
            "partial": partial,
        }

    @staticmethod
    def _normalize(source: SourceSpec, raw: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(raw, Mapping):
            raise SnapshotValidationError("source fragment must be an object")
        observed_at = raw.get("observedAt")
        if not isinstance(observed_at, str) or not _valid_timestamp(observed_at):
            raise SnapshotValidationError("source observation time is missing or invalid")
        source_status = raw.get("sourceStatus", "fresh")
        if source_status not in {"fresh", "stale", "unavailable", "partial"}:
            raise SnapshotValidationError("source status is unknown")
        normalized: dict[str, object] = {"observedAt": observed_at, "sourceStatus": source_status}
        fresh_until = raw.get("freshUntil")
        if fresh_until is not None:
            if not isinstance(fresh_until, str) or not _valid_timestamp(fresh_until):
                raise SnapshotValidationError("source freshness deadline is invalid")
            normalized["freshUntil"] = fresh_until
        for collection in source.collections:
            items = raw.get(collection, [])
            if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
                raise SnapshotValidationError(f"{collection} must be an array of objects")
            normalized[collection] = [_sanitize_mapping(item) for item in items]
        return normalized


_SAFE_KEYS = {
    "id", "name", "title", "summary", "description", "routeId", "domainId", "formalRevisionId", "proposalId", "state",
    "completed", "total", "attentionCount", "projectId", "taskId", "status", "owner", "prerequisiteIds", "blockingReason",
    "updatedAt", "attentionRank", "trigger", "triggerRef", "failure", "target", "tool", "occurredAt", "idempotencyKey",
    "executionId", "role", "lastCheckAt", "subscription", "consumerGroup", "error", "type", "duplicate", "diagnostic",
    "references", "resourceVersionId", "qualification", "requestedScope", "limitations", "candidateSnapshotStatus", "observedAt", "freshUntil", "sourceStatus",
}


def _sanitize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, item in value.items():
        if key not in _SAFE_KEYS:
            continue
        if key in {"error", "summary", "blockingReason", "diagnostic"} and isinstance(item, str):
            sanitized[key] = _safe_message(item)
        else:
            sanitized[key] = _sanitize_value(item)
    return sanitized


_SENSITIVE_PATTERN = re.compile(
    r"(?i)"
    r"\b(?:authorization|bearer|token|secret|password|passwd|api[-_]?key|access[-_]?key|private[-_]?key)\b"
    r"|(?:[A-Za-z]:\\|\\\\[^\s\\]+\\[^\s]+)"  # Windows drive or UNC absolute paths
    r"|(?:\b[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@)"  # URLs carrying inline credentials
)


def _safe_message(value: str) -> str:
    if _SENSITIVE_PATTERN.search(value):
        return "来源错误详情包含敏感信息，已隐藏"
    return " ".join(value.splitlines())[:500]


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _format_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _valid_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _public_error(code: str) -> str:
    messages = {
        "source_not_configured": "来源地址未配置",
        "source_timeout": "查询超时",
        "source_invalid_response": "来源返回格式无效",
        "source_redirect_rejected": "来源返回了跳转，已拒绝请求",
        "source_unavailable": "来源查询暂不可用",
        "source_stale": "来源数据可能过期",
        "source_partial": "来源只返回部分数据",
    }
    return messages.get(code, "来源查询暂不可用")
