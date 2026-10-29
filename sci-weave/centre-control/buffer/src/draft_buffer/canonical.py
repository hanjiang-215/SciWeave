from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize deterministically, refusing NaN/Infinity like the wire format does.

    ``json.dumps`` writes NaN/Infinity by default, which no strict JSON reader
    (including message-envelope's decoder, ai4-onvr) will accept back.
    """
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
