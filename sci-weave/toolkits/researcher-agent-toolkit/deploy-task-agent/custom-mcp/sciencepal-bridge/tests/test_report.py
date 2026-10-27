from __future__ import annotations

import unittest

from sciencepal_bridge.report import build_execution_report, proposed_change_set


def _artifacts() -> list[dict]:
    return [
        {"name": "result.json", "path": "runs/run-1/result.json", "kind": "data", "sha256": "abc123"},
        {"name": "report.md", "path": "runs/run-1/report.md", "kind": "report", "sha256": "def456"},
    ]


def _base(**overrides: object) -> dict:
    values: dict[str, object] = {
        "task_node_id": "task:t1",
        "execution_id": "exec-1",
        "status": "completed",
        "run_id": "run-1",
        "run_elapsed_s": 32.2,
        "summary": "T1 输入检查通过",
        "inputs": [],
        "artifacts": _artifacts(),
        "acceptance": [{"criterion": "150 行", "met": True, "evidence": "result.json.row_count"}],
        "findings": ["输入快照一致"],
        "limitations": ["只验证输入"],
        "route_change": {
            "needed": True,
            "proposal": {"nodes": [{"id": "n2"}], "edges": [{"from": "n1", "to": "n2"}], "rationale": "补一条边"},
        },
    }
    values.update(overrides)
    return values


class ReportValidationTests(unittest.TestCase):
    """ai4-roow: a completed report without a run id or artifact hashes is rejected."""

    def test_completed_report_with_run_id_and_hashes_is_viable(self) -> None:
        report = build_execution_report(**_base())
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["sciencepal"]["run_id"], "run-1")
        self.assertEqual(len(report["artifacts"]), 2)
        self.assertTrue(all(a["sha256"] for a in report["artifacts"]))

    def test_completed_without_run_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_execution_report(**_base(run_id=None))

    def test_completed_without_artifact_hash_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_execution_report(
                **_base(artifacts=[{"name": "result.json", "path": "runs/run-1/result.json", "kind": "data", "sha256": ""}])
            )

    def test_completed_without_any_artifact_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_execution_report(**_base(artifacts=[]))

    def test_failed_report_keeps_run_id_and_may_have_no_artifacts(self) -> None:
        report = build_execution_report(**_base(status="failed", run_id="run-fail", artifacts=[]))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["sciencepal"]["run_id"], "run-fail")
        self.assertEqual(report["artifacts"], [])

    def test_unknown_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_execution_report(**_base(status="running"))

    def test_missing_execution_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_execution_report(**_base(execution_id=""))


class ReportShapeTests(unittest.TestCase):
    def test_schema_version_and_round_trip_fields(self) -> None:
        report = build_execution_report(**_base())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["task_node_id"], "task:t1")
        self.assertEqual(report["execution_id"], "exec-1")
        self.assertEqual(report["sciencepal"]["duration_s"], 32.2)

    def test_acceptance_findings_limitations_are_lists(self) -> None:
        report = build_execution_report(**_base())
        self.assertEqual(len(report["acceptance"]), 1)
        self.assertEqual(report["acceptance"][0]["criterion"], "150 行")
        self.assertEqual(report["findings"], ["输入快照一致"])
        self.assertEqual(report["limitations"], ["只验证输入"])

    def test_route_change_folded_into_proposal(self) -> None:
        report = build_execution_report(**_base())
        self.assertTrue(report["route_change"]["needed"])
        self.assertEqual([node["id"] for node in report["route_change"]["proposal"]["nodes"]], ["n2"])
        self.assertEqual(report["route_change"]["proposal"]["rationale"], "补一条边")

    def test_proposed_change_set_carries_report_ids_and_proposal(self) -> None:
        report = build_execution_report(**_base())
        change_set = proposed_change_set(report)
        self.assertEqual(change_set["task_node_id"], "task:t1")
        self.assertEqual(change_set["execution_id"], "exec-1")
        self.assertEqual(change_set["status"], "completed")
        self.assertEqual([node["id"] for node in change_set["nodes"]], ["n2"])
        self.assertEqual(change_set["rationale"], "补一条边")


if __name__ == "__main__":
    unittest.main()