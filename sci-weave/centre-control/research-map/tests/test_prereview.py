"""Prereview report log tests for the Mapping domain (ai4-qnvd / ai4-oz3s)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from research_mapping.prereview import MappingPrereviewLog, PrereviewLogError, resolve_rule_set
from research_mapping.sqlite_store import SqliteStore


def _rule_set_file(directory: str, version: str) -> Path:
    path = Path(directory) / f"{version}.json"
    path.write_text(json.dumps({"version": version, "checks": ["权限范围", "基准版本", "冲突", "影响范围"]}, ensure_ascii=False), encoding="utf-8")
    return path


class MappingPrereviewLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SqliteStore(os.path.join(self.tmp.name, "prereview.sqlite"))
        self.store.initialize()
        self.rules = os.path.join(self.tmp.name, "rules")
        Path(self.rules).mkdir()
        _rule_set_file(self.rules, "1.0.0")
        self.log = MappingPrereviewLog(self.store, rules_dir=self.rules)

    def _checks(self) -> list[dict[str, object]]:
        return [
            {"name": "权限范围", "verdict": "passed"},
            {"name": "基准版本", "verdict": "passed"},
            {"name": "冲突", "verdict": "passed"},
            {"name": "影响范围", "verdict": "passed"},
        ]

    def test_append_report_is_idempotent_under_unique_key(self) -> None:
        first = self.log.append_report(
            candidate_id="candidate-1", candidate_head="head-a",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        self.assertEqual(first.status, "ok")
        self.assertIsNotNone(first.report_id)
        second = self.log.append_report(
            candidate_id="candidate-1", candidate_head="head-a",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        self.assertTrue(second.duplicate)
        self.assertEqual(second.report_id, first.report_id)
        current = self.log.current_report("candidate-1", "head-a")
        self.assertIsNotNone(current)
        self.assertEqual(current["report_id"], first.report_id)

    def test_report_is_append_only_and_never_edited(self) -> None:
        first = self.log.append_report(
            candidate_id="candidate-2", candidate_head="head-a",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        # A new head produces a NEW report row, never a mutation of the old one.
        second = self.log.append_report(
            candidate_id="candidate-2", candidate_head="head-b",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="failed", conflict_matrix=[],
        )
        self.assertNotEqual(second.report_id, first.report_id)
        old = self.log.current_report("candidate-2", "head-a")
        new = self.log.current_report("candidate-2", "head-b")
        self.assertIsNotNone(old)
        self.assertIsNotNone(new)
        self.assertEqual(new["verdict"], "failed")

    def test_head_moved_decision_invalidates_old_report(self) -> None:
        first = self.log.append_report(
            candidate_id="candidate-3", candidate_head="head-a",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        second = self.log.append_report(
            candidate_id="candidate-3", candidate_head="head-b",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        decision = self.log.append_decision(
            candidate_id="candidate-3", candidate_head="head-a",
            reason="head_moved", superseding_report_id=second.report_id,
        )
        self.assertEqual(decision.reason_code, None)
        self.assertEqual(decision.status, "ok")
        self.assertIsNone(self.log.current_report("candidate-3", "head-a"))
        self.assertIsNotNone(self.log.current_report("candidate-3", "head-b"))

    def test_base_moved_decision_blocks_but_is_appended(self) -> None:
        self.log.append_report(
            candidate_id="candidate-4", candidate_head="head-a",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        decision = self.log.append_decision(
            candidate_id="candidate-4", candidate_head="head-a",
            reason="base_moved",
        )
        self.assertEqual(decision.status, "ok")
        self.assertIsNone(self.log.current_report("candidate-4", "head-a"))

    def test_head_moved_requires_superseding_report(self) -> None:
        self.log.append_report(
            candidate_id="candidate-5", candidate_head="head-a",
            base_formal_revision_id="rev-1", rule_set_version="1.0.0",
            checks=self._checks(), verdict="passed", conflict_matrix=[],
        )
        with self.assertRaises(PrereviewLogError) as ctx:
            self.log.append_decision(
                candidate_id="candidate-5", candidate_head="head-a", reason="head_moved",
            )
        self.assertEqual(ctx.exception.reason_code, "invalid_arguments")

    def test_rule_set_missing_refuses_to_write(self) -> None:
        missing = MappingPrereviewLog(self.store, rules_dir=self.rules)
        with self.assertRaises(PrereviewLogError) as ctx:
            missing.append_report(
                candidate_id="candidate-6", candidate_head="head-a",
                base_formal_revision_id="rev-1", rule_set_version="9.9.9",
                checks=self._checks(), verdict="passed", conflict_matrix=[],
            )
        self.assertEqual(ctx.exception.reason_code, "rule_set_missing")

    def test_rule_set_missing_without_config(self) -> None:
        unconfigured = MappingPrereviewLog(self.store, rules_dir=None)
        with self.assertRaises(PrereviewLogError) as ctx:
            unconfigured.append_report(
                candidate_id="candidate-7", candidate_head="head-a",
                base_formal_revision_id="rev-1", rule_set_version="1.0.0",
                checks=self._checks(), verdict="passed", conflict_matrix=[],
            )
        self.assertEqual(ctx.exception.reason_code, "rule_set_missing")

    def test_resolve_rule_set_reads_name_list(self) -> None:
        document = resolve_rule_set(self.rules, "1.0.0")
        self.assertEqual(document["version"], "1.0.0")
        self.assertIn("权限范围", document["checks"])


if __name__ == "__main__":
    unittest.main()

class ReReviewAfterBaseMovedTests(unittest.TestCase):
    """ai4-sf8l: a base move must let the same head be judged again."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SqliteStore(os.path.join(self.tmp.name, "prereview.sqlite"))
        self.store.initialize()
        self.rules = os.path.join(self.tmp.name, "rules")
        Path(self.rules).mkdir()
        _rule_set_file(self.rules, "1.0.0")
        self.log = MappingPrereviewLog(self.store, rules_dir=self.rules)

    def _report(self, base: str, verdict: str = "passed"):
        checks = [{"name": "基准版本", "verdict": verdict}]
        return self.log.append_report(
            candidate_id="candidate-1", candidate_head="head-a",
            base_formal_revision_id=base, rule_set_version="1.0.0",
            checks=checks, verdict=verdict, conflict_matrix=[],
        )

    def test_re_review_after_base_moved_appends_a_new_report(self) -> None:
        first = self._report("rev-1")
        self.log.append_decision(
            candidate_id="candidate-1", candidate_head="head-a", reason="base_moved"
        )
        self.assertEqual(
            self.store.prereview_status("candidate-1", "head-a")["status"], "report_stale"
        )

        second = self._report("rev-2", verdict="failed")

        self.assertNotEqual(second.report_id, first.report_id)
        self.assertFalse(second.duplicate)
        status = self.store.prereview_status("candidate-1", "head-a")
        self.assertEqual(status["status"], "report_current")
        self.assertEqual(status["base_formal_revision_id"], "rev-2")
        self.assertEqual(status["verdict"], "failed")

    def test_same_head_rules_and_base_is_still_a_duplicate(self) -> None:
        first = self._report("rev-1")
        second = self._report("rev-1")

        self.assertEqual(second.report_id, first.report_id)
        self.assertTrue(second.duplicate)