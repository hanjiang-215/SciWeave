"""Append-only prereview report log for a Mapping domain (ai4-oz3s).

The Centre Agent writes prereview conclusions back into the domain governance
record. This module owns the append-only semantics: a report row is never
edited, the unique key (candidate_id, candidate_head, rule_set_version,
base_formal_revision_id) makes re-review idempotent, and invalidation is an
appended decision row rather than a mutation of the old report. The base
revision is in the key so a re-review after ``base_moved`` appends a new report
instead of colliding with the invalidated one (ai4-sf8l). Rule-set resolution
is delegated to a repository-managed rule file located through configuration;
an unresolvable version must fail with ``rule_set_missing`` instead of writing
an unjustifiable report.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class PrereviewLogStore(Protocol):
    def append_prereview_report(
        self, *, report_id: str, candidate_id: str, candidate_head: str,
        base_formal_revision_id: str | None, rule_set_version: str, checks: str,
        verdict: str, conflict_matrix: str, created_at: str,
    ) -> dict[str, object]: ...

    def append_prereview_decision(
        self, *, decision_id: str, target_report_id: str, reason: str,
        superseding_report_id: str | None, decided_at: str,
    ) -> dict[str, object]: ...

    def current_prereview_report(self, candidate_id: str, candidate_head: str) -> dict | None: ...

    def prereview_status(self, candidate_id: str, candidate_head: str) -> dict[str, object]: ...


@dataclass(frozen=True)
class PrereviewOutcome:
    status: str
    report_id: str | None = None
    decision_id: str | None = None
    candidate_id: str | None = None
    duplicate: bool = False
    reason_code: str | None = None


class PrereviewLogError(RuntimeError):
    """Stable prereview log failure with a machine-readable reason."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_rule_set(rules_dir: str | None, version: str) -> dict[str, Any]:
    """Resolve one rule-set version to its rule file; fail when unresolvable.

    The rule file is a JSON document in the configured rules directory named
    ``<version>.json`` carrying at least ``version`` and ``checks`` (list of
    check names). Only the names list is needed here; rule bodies live in the
    repository and are not copied into reports.
    """
    if not rules_dir or not version:
        raise PrereviewLogError("rule_set_missing", "rule set configuration is required")
    path = Path(rules_dir).expanduser().resolve() / f"{version}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrereviewLogError("rule_set_missing", f"cannot resolve rule set {version}") from exc
    if (
        not isinstance(document, dict)
        or document.get("version") != version
        or not isinstance(document.get("checks"), list)
        or not document["checks"]
        or not all(isinstance(name, str) and name for name in document["checks"])
    ):
        raise PrereviewLogError("rule_set_missing", f"invalid rule set {version}")
    return document


class MappingPrereviewLog:
    """Append prereview reports and invalidation decisions for Mapping."""

    def __init__(self, store: PrereviewLogStore, *, rules_dir: str | None) -> None:
        self._store = store
        self._rules_dir = rules_dir

    def append_report(
        self,
        *,
        candidate_id: str,
        candidate_head: str,
        base_formal_revision_id: str | None,
        rule_set_version: str,
        checks: list[dict[str, Any]],
        verdict: str,
        conflict_matrix: list[dict[str, Any]] | None,
    ) -> PrereviewOutcome:
        if not candidate_id or not candidate_head or not rule_set_version:
            raise PrereviewLogError("invalid_arguments", "candidate_id, candidate_head and rule_set_version are required")
        if verdict not in {"passed", "failed"}:
            raise PrereviewLogError("invalid_arguments", "verdict must be passed or failed")
        if not isinstance(checks, list) or not checks:
            raise PrereviewLogError("invalid_arguments", "checks must be a non-empty array")
        for check in checks:
            if not isinstance(check, dict) or not check.get("name") or not check.get("verdict"):
                raise PrereviewLogError("invalid_arguments", "each check needs name and verdict")
        resolve_rule_set(self._rules_dir, rule_set_version)
        existing = self._store.current_prereview_report(candidate_id, candidate_head)
        if (
            existing is not None
            and existing.get("rule_set_version") == rule_set_version
            and (existing.get("base_formal_revision_id") or "") == (base_formal_revision_id or "")
        ):
            # Same head, same rules, same base: the conclusion cannot differ.
            return PrereviewOutcome("ok", report_id=str(existing["report_id"]),
                                    candidate_id=candidate_id, duplicate=True)
        report_id = "prereview-" + uuid.uuid4().hex
        row = self._store.append_prereview_report(
            report_id=report_id,
            candidate_id=candidate_id,
            candidate_head=candidate_head,
            base_formal_revision_id=base_formal_revision_id or "",
            rule_set_version=rule_set_version,
            checks=json.dumps(checks, ensure_ascii=False, sort_keys=True),
            verdict=verdict,
            conflict_matrix=json.dumps(conflict_matrix or [], ensure_ascii=False, sort_keys=True),
            created_at=_now(),
        )
        return PrereviewOutcome("ok", report_id=str(row["report_id"]), candidate_id=candidate_id)

    def append_decision(
        self,
        *,
        candidate_id: str,
        candidate_head: str,
        reason: str,
        superseding_report_id: str | None = None,
    ) -> PrereviewOutcome:
        if reason not in {"head_moved", "base_moved"}:
            raise PrereviewLogError("invalid_arguments", "reason must be head_moved or base_moved")
        if reason == "head_moved" and not superseding_report_id:
            raise PrereviewLogError("invalid_arguments", "head_moved requires superseding_report_id")
        report = self._store.current_prereview_report(candidate_id, candidate_head)
        if report is None:
            raise PrereviewLogError("report_not_found", "no current report for this candidate head")
        decision_id = "decision-" + uuid.uuid4().hex
        row = self._store.append_prereview_decision(
            decision_id=decision_id,
            target_report_id=str(report["report_id"]),
            reason=reason,
            superseding_report_id=superseding_report_id,
            decided_at=_now(),
        )
        return PrereviewOutcome("ok", decision_id=str(row["decision_id"]),
                                report_id=str(report["report_id"]), candidate_id=candidate_id)

    def current_report(self, candidate_id: str, candidate_head: str) -> dict | None:
        return self._store.current_prereview_report(candidate_id, candidate_head)

    def status_for_candidate(self, candidate_id: str, candidate_head: str) -> dict[str, str]:
        """Derive the observable prereview state of one candidate head.

        The state is a projection of the append-only report log (ai4-oz3s):
        ``missing_report`` when no report exists, ``report_current`` when a
        report is the latest conclusion for this head, or ``report_stale``
        when the latest decision invalidates it (head moved or base moved).
        This is what the management surface returns so an Owner can see a
        candidate blocked on a missing report instead of seeing nothing.
        """
        return self._store.prereview_status(candidate_id, candidate_head)