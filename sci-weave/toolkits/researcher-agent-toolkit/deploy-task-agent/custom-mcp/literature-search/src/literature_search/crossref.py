"""Crossref REST parsing.

Crossref needs no key. Its records carry ``license[].URL`` when the publisher
deposited one and ``abstract`` only sometimes (JATS XML when present), so both
fields are returned as-is or as ``null``/``""`` rather than invented.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import LiteratureConfig
from .errors import LiteratureError, invalid_arguments
from .http import fetch

# Crossref sometimes returns an abstract wrapped in JATS markup.
_JATS_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
# After unescaping, markup that was written as &lt;b&gt; reappears as a tag.
# Only strip a known set: a blanket "<[^>]+>" would eat legitimate text such as
# "x < y and z > w", which appears in math-heavy abstracts.
_ESCAPED_FORMATTING = re.compile(r"</?(?:b|i|em|strong|u|sub|sup|p)\b[^>]*>", re.IGNORECASE)


def _clean_abstract(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    text = _JATS_TAG.sub(" ", raw)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = _ESCAPED_FORMATTING.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _date(item: dict[str, Any]) -> str:
    for key in ("published", "published-print", "issued", "created"):
        block = item.get(key)
        if not isinstance(block, dict):
            continue
        parts = block.get("date-parts")
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            continue
        values = [str(part) for part in parts[0] if part is not None]
        if not values:
            continue
        year = values[0]
        month = values[1].zfill(2) if len(values) > 1 else "01"
        day = values[2].zfill(2) if len(values) > 2 else "01"
        return f"{year}-{month}-{day}"
    return ""


def _authors(item: dict[str, Any]) -> list[str]:
    people = item.get("author")
    if not isinstance(people, list):
        return []
    names = []
    for person in people:
        if not isinstance(person, dict):
            continue
        name = person.get("name")
        if isinstance(name, str) and name.strip():
            names.append(" ".join(name.split()))
            continue
        given = person.get("given")
        family = person.get("family")
        joined = " ".join(part for part in (given, family) if isinstance(part, str) and part.strip())
        if joined:
            names.append(" ".join(joined.split()))
    return names


def _license(item: dict[str, Any]) -> str | None:
    entries = item.get("license")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict):
            url = entry.get("URL")
            if isinstance(url, str) and url.strip():
                return url.strip()
    return None


def _item_to_result(item: dict[str, Any]) -> dict[str, Any]:
    doi = item.get("DOI")
    doi = doi.strip() if isinstance(doi, str) else ""
    url = item.get("URL")
    url = url.strip() if isinstance(url, str) and url.strip() else (f"https://doi.org/{doi}" if doi else "")
    title = _first(item.get("title"))
    return {
        "title": " ".join(title.split()) if isinstance(title, str) else "",
        "authors": _authors(item),
        "published": _date(item),
        "id": doi,
        "abstract": _clean_abstract(item.get("abstract")),
        "url": url,
        "source": "crossref",
    }


def _payload(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise LiteratureError("literature_bad_response", "Crossref returned a body that is not JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
        raise LiteratureError("literature_bad_response", "Crossref returned JSON without a message object")
    return data["message"]


def search(
    query: str,
    limit: int,
    config: LiteratureConfig,
    *,
    transport: Any = None,
) -> list[dict[str, Any]]:
    if not query.strip():
        raise invalid_arguments("query must not be empty")
    body = fetch(
        config.crossref_endpoint,
        {"query": query.strip(), "rows": limit},
        config,
        transport=transport,
    )
    items = _payload(body).get("items")
    if not isinstance(items, list):
        raise LiteratureError("literature_bad_response", "Crossref returned no items array")
    return [_item_to_result(item) for item in items if isinstance(item, dict)][:limit]


def get_abstract(
    doi: str,
    config: LiteratureConfig,
    *,
    transport: Any = None,
) -> dict[str, Any]:
    body = fetch(f"{config.crossref_endpoint.rstrip('/')}/{doi}", {}, config, transport=transport)
    message = _payload(body)
    result = _item_to_result(message)
    return {
        "title": result["title"],
        "abstract": result["abstract"],
        "authors": result["authors"],
        "published": result["published"],
        "url": result["url"],
        # null means Crossref has no deposited license, not "public domain".
        "license": _license(message),
        "source": "crossref",
        "id": result["id"],
    }
