"""Prereview report log tests for the Wiki domain (ai4-qnvd / ai4-oz3s)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from llm_wiki.prereview import PrereviewLogError, WikiPrereviewLog, resolve_rule_set
from llm_wiki.sqlite_store import SqliteStore


def _rule_set_file(directory: str, version: str) -> Path:
    path = Path(directory) / f"{version}.json"
    path.write_text(json.dumps({"version": version, "checks": ["权限范围", "基准版本", "冲突", "影响范围"]}, ensure_ascii=False), encoding="utf-8")
    return path


class WikiPrereviewLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SqliteStore(os.path.join(self.tmp.name, "prereview.sqlite"))
        self.store.initialize()
        self.rules = os.path.join(self.tmp.name, "rules")
        Path(self.rules).mkdir()
        _rule_set_file(self.rules, "1.0.0")
        self.log = WikiPrereviewLog(self.store, rules_dir=self.rules)

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
            candidate_id="candidate-4", candidate_head="head-a", reason="base_moved",
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
        with self.assertRaises(PrereviewLogError) as ctx:
            self.log.append_report(
                candidate_id="candidate-6", candidate_head="head-a",
                base_formal_revision_id="rev-1", rule_set_version="9.9.9",
                checks=self._checks(), verdict="passed", conflict_matrix=[],
            )
        self.assertEqual(ctx.exception.reason_code, "rule_set_missing")

    def test_rule_set_missing_without_config(self) -> None:
        unconfigured = WikiPrereviewLog(self.store, rules_dir=None)
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