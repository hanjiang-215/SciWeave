"""HTTP access with the retry and error policy the card promises.

One tool call retries a failing upstream at most :data:`config.MAX_RETRIES`
times and gives up once :data:`config.TOTAL_TIMEOUT_SECONDS` has elapsed, so an
agent never waits on a hung connection. Every failure leaves as a
:class:`~literature_search.errors.LiteratureError` with a stable code.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .config import MAX_RETRIES, TOTAL_TIMEOUT_SECONDS, LiteratureConfig
from .errors import LiteratureError

# Retryable: the upstream is telling us "later", not "never".
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _classify_status(status: int) -> LiteratureError:
    if status == 404:
        return LiteratureError("literature_not_found", "the upstream has no record for that id")
    if status in _RETRYABLE_STATUS:
        return LiteratureError("literature_unavailable", f"upstream answered {status}")
    return LiteratureError("literature_request_rejected", f"upstream rejected the request ({status})")


def fetch(
    url: str,
    params: dict[str, Any],
    config: LiteratureConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """GET ``url`` and return the body, retrying transient failures.

    ``transport`` exists so tests can inject an ``httpx.MockTransport`` and
    never touch the network.
    """
    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
    headers = {"User-Agent": config.user_agent(), "Accept": "*/*"}
    last_error: LiteratureError | None = None

    for attempt in range(MAX_RETRIES + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            with httpx.Client(
                timeout=min(config.timeout_seconds, remaining),
                follow_redirects=True,
                transport=transport,
            ) as client:
                response = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException:
            last_error = LiteratureError("literature_timeout", "the upstream did not answer in time")
        except httpx.HTTPError as error:
            last_error = LiteratureError("literature_unavailable", f"could not reach the upstream: {type(error).__name__}")
        else:
            if response.status_code == 200:
                return response.text
            last_error = _classify_status(response.status_code)
            if response.status_code not in _RETRYABLE_STATUS:
                raise last_error

        if attempt < MAX_RETRIES:
            # Back off a little, but never past the deadline.
            pause = min(0.2 * (attempt + 1), max(0.0, deadline - time.monotonic()))
            if pause:
                time.sleep(pause)

    raise last_error or LiteratureError("literature_timeout", "the call exceeded its time budget")
