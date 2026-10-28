"""Parsing and id handling; both sources, both id shapes."""

from __future__ import annotations

import unittest

from literature_search import arxiv, crossref
from literature_search.errors import LiteratureError

from . import support


class ArxivParsingTests(unittest.TestCase):
    def test_a_search_returns_the_card_fields(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        items = arxiv.search("transformer", 5, support.config(), transport=recorder.transport)
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(
            set(first),
            {"title", "authors", "published", "id", "abstract", "url", "source"},
        )
        self.assertEqual(first["title"], "Attention Is All You Need")
        self.assertEqual(first["id"], "1706.03762v7")
        self.assertEqual(first["authors"], ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"])
        self.assertEqual(first["published"], "2017-06-12T17:57:34Z")
        self.assertEqual(first["source"], "arxiv")
        self.assertEqual(first["url"], "http://arxiv.org/abs/1706.03762v7")
        self.assertTrue(first["abstract"].startswith("The dominant sequence transduction"))

    def test_the_query_is_scoped_to_all_fields(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        arxiv.search("graph neural network", 3, support.config(), transport=recorder.transport)
        url = recorder.requests[0].url
        self.assertEqual(url.params["search_query"], "all:graph neural network")
        self.assertEqual(url.params["max_results"], "3")
        self.assertEqual(url.params["start"], "0")

    def test_a_whitespace_heavy_feed_still_parses_cleanly(self) -> None:
        """Atom wraps summaries across lines; the card promises one line."""
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        items = arxiv.search("transformer", 2, support.config(), transport=recorder.transport)
        for item in items:
            with self.subTest(id=item["id"]):
                self.assertNotIn("\n", item["abstract"])
                self.assertNotIn("  ", item["title"])

    def test_an_empty_feed_is_an_empty_list_not_an_error(self) -> None:
        recorder = support.respond(support.fixture("arxiv_empty.xml"))
        self.assertEqual(arxiv.search("nothing at all", 5, support.config(), transport=recorder.transport), [])

    def test_a_non_atom_body_is_a_stable_error(self) -> None:
        recorder = support.respond("<html>rate limited</html>")
        with self.assertRaises(LiteratureError) as caught:
            arxiv.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_bad_response")

    def test_a_missing_abstract_returns_null_license_never_a_guess(self) -> None:
        recorder = support.respond(support.fixture("arxiv_search.xml"))
        record = arxiv.get_abstract("1706.03762", support.config(), transport=recorder.transport)
        self.assertIsNone(record["license"])
        self.assertEqual(record["source"], "arxiv")
        self.assertEqual(record["id"], "1706.03762v7")

    def test_an_unknown_id_is_not_found(self) -> None:
        recorder = support.respond(support.fixture("arxiv_empty.xml"))
        with self.assertRaises(LiteratureError) as caught:
            arxiv.get_abstract("1706.03762", support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_not_found")

    def test_a_url_or_arxiv_prefix_is_normalized_away(self) -> None:
        for value in (
            "https://arxiv.org/abs/1706.03762",
            "http://arxiv.org/abs/1706.03762",
            "arXiv:1706.03762",
            "1706.03762",
        ):
            with self.subTest(value=value):
                self.assertEqual(arxiv.normalize_arxiv_id(value), "1706.03762")


class IdShapeTests(unittest.TestCase):
    def test_new_style_ids_are_recognized(self) -> None:
        for value in ("1706.03762", "1706.03762v7", "2601.00001"):
            with self.subTest(value=value):
                self.assertTrue(arxiv.looks_like_arxiv_id(value))

    def test_old_style_ids_are_recognized(self) -> None:
        for value in ("hep-th/9901001", "cs/0112017", "math.HO/0501001"):
            with self.subTest(value=value):
                self.assertTrue(arxiv.looks_like_arxiv_id(value))

    def test_dois_are_recognized(self) -> None:
        for value in ("10.1038/nature14539", "10.1049/ic:19981011"):
            with self.subTest(value=value):
                self.assertTrue(arxiv.looks_like_doi(value))

    def test_a_doi_is_never_mistaken_for_an_arxiv_id(self) -> None:
        self.assertFalse(arxiv.looks_like_arxiv_id("10.1038/nature14539"))
        self.assertEqual(arxiv.id_kind("10.1038/nature14539"), "crossref")

    def test_an_arxiv_id_is_never_mistaken_for_a_doi(self) -> None:
        self.assertFalse(arxiv.looks_like_doi("1706.03762"))
        self.assertEqual(arxiv.id_kind("1706.03762"), "arxiv")

    def test_something_that_is_neither_fails_with_a_stable_code(self) -> None:
        with self.assertRaises(LiteratureError) as caught:
            arxiv.id_kind("some paper title")
        self.assertEqual(caught.exception.code, "invalid_arguments")


class CrossrefParsingTests(unittest.TestCase):
    def test_a_search_returns_the_card_fields(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        items = crossref.search("transformer", 5, support.config(), transport=recorder.transport)
        self.assertEqual(len(items), 2)
        for item in items:
            with self.subTest(id=item["id"]):
                self.assertEqual(
                    set(item),
                    {"title", "authors", "published", "id", "abstract", "url", "source"},
                )
                self.assertEqual(item["source"], "crossref")

    def test_a_record_without_an_abstract_gets_an_empty_string(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        items = crossref.search("transformer", 5, support.config(), transport=recorder.transport)
        self.assertEqual(items[0]["abstract"], "")

    def test_a_jats_abstract_is_flattened_to_plain_text(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        items = crossref.search("transformer", 5, support.config(), transport=recorder.transport)
        abstract = items[1]["abstract"]
        self.assertNotIn("<jats:p>", abstract)
        self.assertNotIn("<b>", abstract)
        self.assertIn("composed of multiple layers", abstract)

    def test_a_partial_date_becomes_an_iso_date(self) -> None:
        recorder = support.respond(support.fixture("crossref_search.json"))
        items = crossref.search("transformer", 5, support.config(), transport=recorder.transport)
        self.assertEqual(items[0]["published"], "1998-01-01")
        self.assertEqual(items[1]["published"], "2015-05-27")

    def test_the_doi_is_the_id_and_the_url_defaults_to_the_doi(self) -> None:
        recorder = support.respond(support.fixture("crossref_work.json"))
        record = crossref.get_abstract("10.1038/nature14539", support.config(), transport=recorder.transport)
        self.assertEqual(record["id"], "10.1038/nature14539")
        self.assertEqual(record["url"], "https://doi.org/10.1038/nature14539")

    def test_a_deposited_license_is_returned(self) -> None:
        recorder = support.respond(support.fixture("crossref_work.json"))
        record = crossref.get_abstract("10.1038/nature14539", support.config(), transport=recorder.transport)
        self.assertEqual(record["license"], "https://www.nature.com/articles/nature14539")

    def test_no_deposited_license_is_null_not_a_guess(self) -> None:
        recorder = support.respond(support.fixture("crossref_work_no_license.json"))
        record = crossref.get_abstract("10.1049/ic:19981011", support.config(), transport=recorder.transport)
        self.assertIsNone(record["license"])

    def test_the_single_record_endpoint_is_the_works_url_plus_the_doi(self) -> None:
        recorder = support.respond(support.fixture("crossref_work.json"))
        crossref.get_abstract("10.1038/nature14539", support.config(), transport=recorder.transport)
        self.assertEqual(str(recorder.requests[0].url), "https://crossref.test/works/10.1038/nature14539")

    def test_a_body_without_a_message_object_is_a_stable_error(self) -> None:
        recorder = support.respond('{"status": "ok"}')
        with self.assertRaises(LiteratureError) as caught:
            crossref.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_bad_response")

    def test_a_body_that_is_not_json_is_a_stable_error(self) -> None:
        recorder = support.respond("not json at all")
        with self.assertRaises(LiteratureError) as caught:
            crossref.search("x", 1, support.config(), transport=recorder.transport)
        self.assertEqual(caught.exception.code, "literature_bad_response")


if __name__ == "__main__":
    unittest.main()
