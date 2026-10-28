"""The failure policy the card promises: stable codes, bounded retries, no hangs."""

from __future__ import annotations

import unittest

import httpx

from literature_search import arxiv, crossref
from literature_search.config import MAX_RETRIES
from literature_search.errors import LiteratureError

from . import support


class StatusMappingTests(unittest.TestCase):
    def test_a_404_is_not_found(self) -> None:
        recorder = support.respond("missing", status=404)
        with self.assertRaises(LiteratureError) as caught:
            arxiv.get_abstract("1706.03762", support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_not_found")

    def test_a_403_is_rejected_not_retried(self) -> None:
        recorder = support.respond("forbidden", status=403)
        with self.assertRaises(LiteratureError) as caught:
            arxiv.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_request_rejected")
        self.assertEqual(len(recorder.requests), 1, "a 4xx that is not 429 must not be retried")

    def test_a_400_is_rejected(self) -> None:
        recorder = support.respond("bad", status=400)
        with self.assertRaises(LiteratureError) as caught:
            crossref.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_request_rejected")

    def test_a_500_after_retries_is_unavailable(self) -> None:
        recorder = support.respond("boom", status=500)
        with self.assertRaises(LiteratureError) as caught:
            arxiv.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_unavailable")
        self.assertEqual(len(recorder.requests), MAX_RETRIES + 1)

    def test_a_transient_503_then_success_recovers(self) -> None:
        recorder = support.respond_sequence(
            (503, "later"),
            (200, support.fixture("arxiv_search.xml")),
        )
        items = arxiv.search("transformer", 2, support.config(), transport=recorder.transport)
        self.assertEqual(len(items), 2)
        self.assertEqual(len(recorder.requests), 2)

    def test_a_429_is_retried(self) -> None:
        recorder = support.respond_sequence(
            (429, "slow down"),
            (200, support.fixture("crossref_search.json")),
        )
        items = crossref.search("transformer", 2, support.config(), transport=recorder.transport)
        self.assertEqual(len(items), 2)
        self.assertEqual(len(recorder.requests), 2)

    def test_a_timeout_is_a_stable_code(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow")

        recorder = support.Recorder(handler)
        with self.assertRaises(LiteratureError) as caught:
            arxiv.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_timeout")
        self.assertEqual(len(recorder.requests), MAX_RETRIES + 1)

    def test_a_connection_error_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        recorder = support.Recorder(handler)
        with self.assertRaises(LiteratureError) as caught:
            crossref.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_unavailable")


class RequestShapeTests(unittest.TestCase):
    def test_arxiv_follows_the_301_to_https(self) -> None:
        """export.arxiv.org answers a plain query with a 301; httpx must follow it."""
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        arxiv.search("x", 1, support.config(), transport=recorder.transport)
        self.assertTrue(recorder.requests[0].url.scheme == "https")

    def test_the_user_agent_identifies_the_service_and_the_contact(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        arxiv.search("x", 1, support.config(contact_email="dev@example.org"), transport=recorder.transport)
        agent = recorder.requests[0].headers["User-Agent"]
        self.assertIn("sciweave-literature-search", agent)
        self.assertIn("mailto:dev@example.org", agent)

    def test_no_contact_email_means_no_mailto_noise(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        arxiv.search("x", 1, support.config(contact_email=""), transport=recorder.transport)
        self.assertNotIn("mailto:", recorder.requests[0].headers["User-Agent"])

    def test_the_endpoints_are_overridable(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        arxiv.search(
            "x",
            1,
            support.config(arxiv_endpoint="https://mirror.example/query"),
            transport=recorder.transport,
        )
        self.assertEqual(recorder.requests[0].url.host, "mirror.example")

    def test_the_crossref_contact_email_is_never_sent_without_being_configured(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        crossref.search("x", 1, support.config(), transport=recorder.transport)
        self.assertNotIn("mailto:", recorder.requests[0].headers["User-Agent"])


if __name__ == "__main__":
    unittest.main()
