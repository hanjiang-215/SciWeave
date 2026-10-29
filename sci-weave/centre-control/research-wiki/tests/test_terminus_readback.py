"""Regression tests for the three defects found during the 2026-10-29 E2E round.

They are all read-back comparison problems that made a *successful* TerminusDB
write look like ``store_result_unknown`` once the store added its own fields:

- D1: ``_request`` routed a 5-argument ``(method, url, headers, body, timeout)``
  write through the 3-argument GET-only opener and raised ``TypeError``.
- D2: the read-back compared whole documents, so the server-assigned ``@id`` that
  the submitted document lacks made an identical document compare unequal.
- D3 (research-map): ``@type: Set`` members come back in canonical sorted order,
  so an unsorted submission failed the whole-document comparison.

D1 and D2 live in research-wiki; D3 lives in research-map. See
``技术缺陷报告.md`` for the field report.
"""

from __future__ import annotations

import json
import unittest

from llm_wiki import terminus_store as wiki_store
from llm_wiki.candidate_submission import _contains as wiki_contains


class _D1OpenerTests(unittest.TestCase):
    """D1: the default request opener accepts (method, url, headers, body, timeout)."""

    def test_default_request_opener_sends_method_and_body(self):
        from llm_wiki.terminus_store import TerminusDBWikiCandidateStore

        store = TerminusDBWikiCandidateStore(store_id="s", database="d", base_url="http://unused")
        # The default opener must have the 5-argument request signature, not the
        # 3-argument GET-only shape. A bad default raised TypeError on every write.
        import inspect

        params = list(inspect.signature(store._request_opener).parameters)
        self.assertEqual(params, ["method", "url", "headers", "body", "timeout"])

    def test_request_routes_through_the_injectable_opener(self):
        from llm_wiki.terminus_store import TerminusDBWikiCandidateStore

        seen = []

        def opener(method, url, headers, body, timeout):
            seen.append((method, url, body))
            return 200, {}, b"{}"

        store = TerminusDBWikiCandidateStore(
            store_id="s", database="d", base_url="http://unused", request_opener=opener
        )
        status, _, _ = store._request("POST", "http://unused/api/document", b"payload")
        self.assertEqual(status, 200)
        self.assertEqual(seen, [("POST", "http://unused/api/document", b"payload")])


class _D2WikiMatchTests(unittest.TestCase):
    """D2: read-back ignores the server-assigned @id."""

    def test_documents_match_tolerates_server_assigned_id(self):
        expected = [{"@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t", "body_markdown": "b"}]
        actual = [{"@id": "WikiRevision/r1", "@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t", "body_markdown": "b"}]
        self.assertTrue(wiki_store._candidate_documents_match(actual, expected))

    def test_documents_match_still_rejects_content_difference(self):
        expected = [{"@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t", "body_markdown": "b"}]
        actual = [{"@id": "WikiRevision/r1", "@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t", "body_markdown": "DIFFERENT"}]
        self.assertFalse(wiki_store._candidate_documents_match(actual, expected))

    def test_contains_ignores_assigned_id_when_expected_has_none(self):
        expected = [{"@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t"}]
        actual = [{"@id": "WikiRevision/r1", "@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t"}]
        self.assertTrue(wiki_contains(actual, expected))

    def test_contains_still_rejects_content_difference(self):
        expected = [{"@type": "WikiRevision", "wiki_revision_id": "r1", "title": "t"}]
        actual = [{"@id": "WikiRevision/r1", "@type": "WikiRevision", "wiki_revision_id": "r1", "title": "OTHER"}]
        self.assertFalse(wiki_contains(actual, expected))


if __name__ == "__main__":
    unittest.main()
