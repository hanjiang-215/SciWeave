"""Shared test doubles: fixtures on disk, a mock transport, never the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx

from literature_search.config import LiteratureConfig

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> dict[str, Any]:
    return json.loads(fixture(name))


def config(**overrides: Any) -> LiteratureConfig:
    values = {
        "arxiv_endpoint": "https://arxiv.test/api/query",
        "crossref_endpoint": "https://crossref.test/works",
        "contact_email": "",
        "timeout_seconds": 5.0,
    }
    values.update(overrides)
    return LiteratureConfig(**values)


class Recorder:
    """Collect the requests a tool made and answer with scripted responses."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def respond(body: str, status: int = 200) -> Recorder:
    return Recorder(lambda request: httpx.Response(status, text=body))


def respond_sequence(*responses: tuple[int, str]) -> Recorder:
    """Answer a sequence of (status, body) pairs, repeating the last one."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, text=body)

    return Recorder(handler)
