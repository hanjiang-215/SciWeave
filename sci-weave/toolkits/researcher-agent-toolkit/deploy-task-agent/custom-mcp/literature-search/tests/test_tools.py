"""The tool layer: argument validation, source dispatch, and the JSON envelope."""

from __future__ import annotations

import json
import unittest

from literature_search import tools
from literature_search.config import MAX_LIMIT

from . import support


class SearchDispatchTests(unittest.TestCase):
    def test_the_default_source_is_arxiv(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        result = tools.call("search", {"query": "transformer"}, support.config(), transport=recorder.transport)
        self.assertEqual(json.loads(result)[0]["source"], "arxiv")
        self.assertEqual(recorder.requests[0].url.host, "arxiv.test")

    def test_crossref_is_reached_when_asked_for(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        result = tools.call(
            "search",
            {"query": "transformer", "source": "crossref", "limit": 2},
            support.config(),
            transport=recorder.transport,
        )
        self.assertEqual(json.loads(result)[0]["source"], "crossref")
        self.assertEqual(recorder.requests[0].url.host, "crossref.test")

    def test_an_unknown_source_is_rejected_without_a_request(self) -> None:
        recorder = support.respond("should not be called")
        result = json.loads(
            tools.call("search", {"query": "x", "source": "google"}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["error"]["code"], "unsupported_source")
        self.assertEqual(recorder.requests, [])

    def test_a_source_case_and_spacing_variant_still_works(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        result = json.loads(
            tools.call("search", {"query": "x", "source": " Crossref "}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result[0]["source"], "crossref")

    def test_an_empty_query_is_invalid_arguments(self) -> None:
        recorder = support.respond("nope")
        result = json.loads(tools.call("search", {"query": "   "}, support.config(), transport=recorder.transport))
        self.assertEqual(result["error"]["code"], "invalid_arguments")
        self.assertEqual(recorder.requests, [])

    def test_a_limit_above_the_cap_fails_loudly_rather_than_truncating(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        result = json.loads(
            tools.call("search", {"query": "x", "limit": MAX_LIMIT + 1}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["error"]["code"], "invalid_arguments")
        self.assertIn(str(MAX_LIMIT), result["error"]["message"])
        self.assertEqual(recorder.requests, [], "an out-of-range limit must not reach the upstream")

    def test_the_cap_itself_is_allowed(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        result = json.loads(
            tools.call("search", {"query": "x", "limit": MAX_LIMIT}, support.config(), transport=recorder.transport)
        )
        self.assertIsInstance(result, list)
        self.assertEqual(recorder.requests[0].url.params["max_results"], str(MAX_LIMIT))

    def test_a_zero_limit_is_invalid(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        result = json.loads(
            tools.call("search", {"query": "x", "limit": 0}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["error"]["code"], "invalid_arguments")


class GetAbstractDispatchTests(unittest.TestCase):
    def test_an_arxiv_id_picks_arxiv_without_a_source(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        result = json.loads(
            tools.call("get_abstract", {"id": "1706.03762"}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["source"], "arxiv")
        self.assertEqual(recorder.requests[0].url.host, "arxiv.test")

    def test_a_doi_picks_crossref_without_a_source(self) -> None:
        recorder = support.respond(support.fixture("crossref_work.json"))
        result = json.loads(
            tools.call("get_abstract", {"id": "10.1038/nature14539"}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["source"], "crossref")
        self.assertEqual(recorder.requests[0].url.host, "crossref.test")

    def test_an_explicit_source_overrides_the_shape(self) -> None:
        recorder = support.respond(support.fixture("crossref_work.json"))
        result = json.loads(
            tools.call(
                "get_abstract",
                {"id": "10.1038/nature14539", "source": "crossref"},
                support.config(),
                transport=recorder.transport,
            )
        )
        self.assertEqual(result["id"], "10.1038/nature14539")

    def test_an_empty_id_is_invalid_arguments(self) -> None:
        recorder = support.respond("nope")
        result = json.loads(tools.call("get_abstract", {"id": ""}, support.config(), transport=recorder.transport))
        self.assertEqual(result["error"]["code"], "invalid_arguments")

    def test_an_unrecognizable_id_says_so(self) -> None:
        recorder = support.respond("nope")
        result = json.loads(
            tools.call("get_abstract", {"id": "Attention Is All You Need"}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["error"]["code"], "invalid_arguments")
        self.assertIn("arXiv id or a DOI", result["error"]["message"])

    def test_the_license_field_is_always_present(self) -> None:
        for fixture, identifier in (
            ("arxiv_search.xml", "1706.03762"),
            ("crossref_work.json", "10.1038/nature14539"),
            ("crossref_work_no_license.json", "10.1049/ic:19981011"),
        ):
            with self.subTest(identifier=identifier):
                recorder = support.respond(support.fixture(fixture))
                result = json.loads(
                    tools.call("get_abstract", {"id": identifier}, support.config(), transport=recorder.transport)
                )
                self.assertIn("license", result)


class EnvelopeTests(unittest.TestCase):
    def test_an_unknown_tool_is_a_stable_error(self) -> None:
        result = json.loads(tools.call("download_paper", {}, support.config()))
        self.assertEqual(result["error"]["code"], "unknown_tool")

    def test_success_is_a_bare_json_array_not_a_wrapper(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        result = tools.call("search", {"query": "x"}, support.config(), transport=recorder.transport)
        self.assertTrue(result.startswith("["))

    def test_a_non_integer_limit_is_invalid_arguments(self) -> None:
        recorder = support.respond("nope")
        result = json.loads(
            tools.call("search", {"query": "x", "limit": "lots"}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(result["error"]["code"], "invalid_arguments")

    def test_errors_are_json_with_a_code_and_a_message(self) -> None:
        recorder = support.respond("gone", status=404)
        result = json.loads(
            tools.call("get_abstract", {"id": "1706.03762"}, support.config(), transport=recorder.transport)
        )
        self.assertEqual(set(result["error"]), {"code", "message"})

    def test_an_unexpected_exception_becomes_a_generic_error_not_a_broken_pipe(self) -> None:
        """A stdio server that raises mid-session leaves the client with no answer."""

        def handler(request):
            raise RuntimeError("unexpected")

        recorder = support.Recorder(handler)
        result = json.loads(tools.call("search", {"query": "x"}, support.config(), transport=recorder.transport))
        self.assertEqual(result["error"]["code"], "literature_internal")
        self.assertNotIn("RuntimeError", result["error"]["message"], "internal details must not leak")


if __name__ == "__main__":
    unittest.main()
