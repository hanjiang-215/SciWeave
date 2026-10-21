from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Return the compact, key-sorted JSON used as content identity."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    """Return the SHA-256 of the canonical JSON representation."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
