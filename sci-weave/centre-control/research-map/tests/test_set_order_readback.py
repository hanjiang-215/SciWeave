"""D3 regression: research-map candidate read-back is insensitive to Set order.

``@type: Set`` fields come back from TerminusDB in canonical (sorted) order. A
candidate submitted with the members in any other order is the same document, so
reconciliation must not fail on member order. See ``技术缺陷报告.md`` defect 3.
"""

from __future__ import annotations

import unittest

from research_mapping.terminus_store import _contains_documents, _normalize_set_fields


class SetOrderReadbackTests(unittest.TestCase):
    def test_normalize_sorts_string_lists_only(self):
        document = {"@id": "TaskNode/n1", "acceptance_criteria": ["b", "a", "c"], "count": 3}
        normalized = _normalize_set_fields(document)
        self.assertEqual(normalized["acceptance_criteria"], ["a", "b", "c"])
        self.assertEqual(normalized["count"], 3)
        self.assertEqual(normalized["@id"], "TaskNode/n1")

    def test_contains_accepts_reordered_set_members(self):
        actual = [{"@id": "TaskNode/n1", "acceptance_criteria": ["a", "b", "c"]}]
        expected = [{"@id": "TaskNode/n1", "acceptance_criteria": ["c", "a", "b"]}]
        self.assertTrue(_contains_documents(actual, expected))

    def test_contains_still_rejects_a_real_difference(self):
        actual = [{"@id": "TaskNode/n1", "acceptance_criteria": ["a", "b"]}]
        expected = [{"@id": "TaskNode/n1", "acceptance_criteria": ["a", "b", "c"]}]
        self.assertFalse(_contains_documents(actual, expected))

    def test_contains_ignores_missing_optional_field_set_order(self):
        actual = [{"@id": "TaskNode/n1", "expected_outputs": ["y", "x"]}]
        expected = [{"@id": "TaskNode/n1", "expected_outputs": ["x", "y"]}]
        self.assertTrue(_contains_documents(actual, expected))


if __name__ == "__main__":
    unittest.main()
