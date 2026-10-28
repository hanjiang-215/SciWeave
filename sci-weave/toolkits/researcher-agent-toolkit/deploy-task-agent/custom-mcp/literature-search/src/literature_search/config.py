"""Configuration; every deployment value comes from the environment.

Both upstreams are public and need no key, so the defaults are usable as-is.
The endpoints stay overridable because tests must not reach the network and a
deployment behind a gateway needs a mirror.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
DEFAULT_CROSSREF_ENDPOINT = "https://api.crossref.org/works"

DEFAULT_LIMIT = 5
MAX_LIMIT = 20

# One tool call may retry at most twice and must finish inside this budget.
MAX_RETRIES = 2
TOTAL_TIMEOUT_SECONDS = 30.0


class ConfigError(ValueError):
    """Stable configuration error; the code is safe to show to an agent."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _timeout(env: dict[str, str]) -> float:
    raw = (env.get("LITERATURE_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return 10.0
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError("invalid_config", "LITERATURE_TIMEOUT_SECONDS must be a number") from None
    if not 1.0 <= value <= TOTAL_TIMEOUT_SECONDS:
        raise ConfigError(
            "invalid_config",
            f"LITERATURE_TIMEOUT_SECONDS must be between 1 and {TOTAL_TIMEOUT_SECONDS:g}",
        )
    return value


@dataclass(frozen=True)
class LiteratureConfig:
    arxiv_endpoint: str
    crossref_endpoint: str
    contact_email: str
    timeout_seconds: float

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "LiteratureConfig":
        source = os.environ if env is None else env
        return cls(
            arxiv_endpoint=(source.get("LITERATURE_ARXIV_ENDPOINT") or "").strip()
            or DEFAULT_ARXIV_ENDPOINT,
            crossref_endpoint=(source.get("LITERATURE_CROSSREF_ENDPOINT") or "").strip()
            or DEFAULT_CROSSREF_ENDPOINT,
            contact_email=(source.get("LITERATURE_CONTACT_EMAIL") or "").strip(),
            timeout_seconds=_timeout(source),
        )

    def user_agent(self) -> str:
        """Crossref asks for a contact address; both sources ask for honesty."""
        contact = f" (mailto:{self.contact_email})" if self.contact_email else ""
        return f"sciweave-literature-search/0.1.0{contact}"
