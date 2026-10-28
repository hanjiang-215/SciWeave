"""arXiv Atom parsing.

The Atom feed carries everything the card needs except the license: the public
API returns no ``arxiv:license`` element at all (checked against 50-entry
category queries and old-style ids), so ``license`` is always ``null`` for
arXiv results rather than guessed from the abs page.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from typing import Any

from .config import MAX_LIMIT, LiteratureConfig
from .errors import LiteratureError, invalid_arguments
from .http import fetch

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"

# New style (1706.03762, 1706.03762v7), old style (hep-th/9901001), and archive
# style (cs/0112017). Anchored so a DOI can never match.
_ARXIV_ID = re.compile(r"^(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_arxiv_id(value: str) -> str:
    """Strip a URL or an ``arXiv:`` prefix; keep the version suffix."""
    text = value.strip()
    for prefix in ("https://arxiv.org/abs/", "http://arxiv.org/abs/", "arxiv.org/abs/", "arXiv:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.strip()


def looks_like_doi(value: str) -> bool:
    return bool(_DOI.match(value.strip()))


def looks_like_arxiv_id(value: str) -> bool:
    return bool(_ARXIV_ID.match(normalize_arxiv_id(value)))


def id_kind(value: str) -> str:
    """Infer the source from an id's shape, or fail with a stable code."""
    text = value.strip()
    if looks_like_doi(text):
        return "crossref"
    if looks_like_arxiv_id(text):
        return "arxiv"
    raise invalid_arguments(f"cannot tell whether {value!r} is an arXiv id or a DOI")


def _text(node: ElementTree.Element | None) -> str:
    return "" if node is None or node.text is None else " ".join(node.text.split())


def _entry_to_item(entry: ElementTree.Element) -> dict[str, Any]:
    raw_id = _text(entry.find(f"{ATOM}id"))
    # The feed's id is a URL with the version suffix: http://arxiv.org/abs/1706.03762v7
    arxiv_id = normalize_arxiv_id(raw_id)
    url = raw_id or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")
    return {
        "title": _text(entry.find(f"{ATOM}title")),
        "authors": [_text(author.find(f"{ATOM}name")) for author in entry.findall(f"{ATOM}author")],
        "published": _text(entry.find(f"{ATOM}published")),
        "id": arxiv_id,
        "abstract": _text(entry.find(f"{ATOM}summary")),
        "url": url,
        "source": "arxiv",
    }


def parse_feed(body: str) -> list[dict[str, Any]]:
    """Parse an Atom feed into card items; an empty feed is not an error."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        raise LiteratureError("literature_bad_response", "arXiv returned a body that is not Atom XML") from None
    if root.tag != f"{ATOM}feed":
        raise LiteratureError("literature_bad_response", "arXiv returned XML that is not an Atom feed")
    return [_entry_to_item(entry) for entry in root.findall(f"{ATOM}entry")]


def check_limit(limit: int) -> int:
    if limit < 1:
        raise invalid_arguments("limit must be at least 1")
    if limit > MAX_LIMIT:
        raise invalid_arguments(f"limit must be at most {MAX_LIMIT}, got {limit}")
    return limit


def search(
    query: str,
    limit: int,
    config: LiteratureConfig,
    *,
    transport: Any = None,
) -> list[dict[str, Any]]:
    if not query.strip():
        raise invalid_arguments("query must not be empty")
    check_limit(limit)
    body = fetch(
        config.arxiv_endpoint,
        {"search_query": f"all:{query.strip()}", "start": 0, "max_results": limit},
        config,
        transport=transport,
    )
    return parse_feed(body)[:limit]


def get_abstract(
    arxiv_id: str,
    config: LiteratureConfig,
    *,
    transport: Any = None,
) -> dict[str, Any]:
    normalized = normalize_arxiv_id(arxiv_id)
    if not looks_like_arxiv_id(normalized):
        raise invalid_arguments(f"{arxiv_id!r} is not an arXiv id")
    body = fetch(config.arxiv_endpoint, {"id_list": normalized}, config, transport=transport)
    items = parse_feed(body)
    if not items:
        raise LiteratureError("literature_not_found", f"arXiv has no record for {normalized}")
    item = items[0]
    return {
        "title": item["title"],
        "abstract": item["abstract"],
        "authors": item["authors"],
        "published": item["published"],
        "url": item["url"],
        # The public Atom API never returns a license element; null means
        # "not stated by the source", never "public domain".
        "license": None,
        "source": "arxiv",
        "id": item["id"],
    }
