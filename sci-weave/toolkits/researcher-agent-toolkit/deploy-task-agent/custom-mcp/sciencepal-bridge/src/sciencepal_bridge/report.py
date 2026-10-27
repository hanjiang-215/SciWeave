"""ExecutionReport assembly and validation (ai4-roow).

The collaborator bridge owns the deterministic parts of turning one SciencePal
run into an ExecutionReport.  The report is written to the central draft buffer
(namespace ``mapping``, kind ``mapping_change``); it is never written directly
to the formal Research Mapping.  TaskNode owners review, humans submit, and the
Project Owner formalizes.  Run state stays a projection and never enters a
TaskNode version object (L0/L1 boundary, see ai4-roow Design).
"""

from __future__ import annotations

import hashlib
from typing import Any

from .store import RunStore

REPORT_SCHEMA_VERSION = 1

# Completed reports must carry a run id and at least one artifact hash; a
# failure report may keep just the run id and an error code.
_COMPLETED_REQUIRED = ("task_node_id", "execution_id", "sciencepal.run_id")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_execution_report(
    *,
    task_node_id: str,
    execution_id: str,
    status: str,
    run_id: str | None,
    run_elapsed_s: float | None,
    summary: str,
    inputs: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    acceptance: list[dict[str, Any]],
    findings: list[str],
    limitations: list[str],
    route_change: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a validated ExecutionReport from collected run evidence.

    ``inputs`` and ``artifacts`` must already carry ``sha256`` digests (the
    bridge computes them during upload/collect).  A completed report without a
    run id or without any artifact hash is rejected.  Failure reports keep the
    run id and the caller must pass an ``error_code`` via ``summary`` or leave
    artifacts empty; validation only blocks the ``completed`` status.
    """
    if not task_node_id or not str(task_node_id).strip():
        raise ValueError("task_node_id is required")
    if not execution_id or not str(execution_id).strip():
        raise ValueError("execution_id is required")

    status = (status or "").strip().lower()
    if status not in {"completed", "failed", "stopped"}:
        raise ValueError(f"unsupported report status: {status!r}")

    if status == "completed":
        if not run_id:
            raise ValueError("completed report requires sciencepal.run_id")
        if not artifacts or not any(artifact.get("sha256") for artifact in artifacts):
            raise ValueError("completed report requires at least one artifact sha256")

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "task_node_id": str(task_node_id).strip(),
        "execution_id": str(execution_id).strip(),
        "status": status,
        "summary": (summary or "").strip(),
        "sciencepal": {
            "run_id": run_id or None,
            "thread_id": None,
            "agent_id": None,
            "model": None,
            "duration_s": float(run_elapsed_s) if run_elapsed_s is not None else None,
        },
        "inputs": [dict(item) for item in inputs if item.get("name") and item.get("sha256")],
        "artifacts": [
            {
                "name": item["name"],
                "path": item.get("path"),
                "kind": item.get("kind"),
                "sha256": item["sha256"],
            }
            for item in artifacts
            if item.get("name") and item.get("sha256")
        ],
        "acceptance": [
            {"criterion": item["criterion"], "met": bool(item.get("met")), "evidence": item.get("evidence")}
            for item in acceptance
            if item.get("criterion")
        ],
        "findings": [str(item) for item in findings if item],
        "limitations": [str(item) for item in limitations if item],
        "route_change": {
            "needed": bool(route_change.get("needed")) if route_change else False,
            "proposal": {
                "nodes": list(route_change.get("proposal", {}).get("nodes", [])) if route_change else [],
                "edges": list(route_change.get("proposal", {}).get("edges", [])) if route_change else [],
                "rationale": str(route_change.get("proposal", {}).get("rationale", "")) if route_change else "",
            },
        },
    }
    return report


def report_from_run_store(
    store: RunStore,
    run_id: str,
    *,
    task_node_id: str,
    execution_id: str,
    summary: str,
    acceptance: list[dict[str, Any]],
    findings: list[str] | None = None,
    limitations: list[str] | None = None,
    route_change: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a report directly from the local run ledger (store) and artifacts."""
    record = store.get(run_id)
    if record is None:
        raise ValueError(f"run not found in ledger: {run_id}")
    artifacts = store.artifacts(run_id)
    return build_execution_report(
        task_node_id=task_node_id,
        execution_id=execution_id or record.get("execution_id") or run_id,
        status=record["status"],
        run_id=run_id,
        run_elapsed_s=None,
        summary=summary,
        inputs=[],
        artifacts=artifacts,
        acceptance=acceptance,
        findings=findings or [],
        limitations=limitations or [],
        route_change=route_change,
    )


def proposed_change_set(report: dict[str, Any]) -> dict[str, Any]:
    """The change set carried by a mapping_change draft.

    L0 boundary (ai4-roow): the formal map only updates through a candidate
    formalized by the Project Owner.  The change set describes what the report
    would change, and route_change is folded in as the proposal; nothing here
    writes the formal map.
    """
    proposal = report.get("route_change", {}).get("proposal", {})
    return {
        "task_node_id": report.get("task_node_id"),
        "execution_id": report.get("execution_id"),
        "status": report.get("status"),
        "nodes": proposal.get("nodes", []),
        "edges": proposal.get("edges", []),
        "rationale": proposal.get("rationale", ""),
    }
