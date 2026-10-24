from __future__ import annotations

import json
import sys
from typing import Callable, Any


def run(dispatch: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Serve MCP JSON-RPC requests over newline-delimited stdio."""
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            response = dispatch(request)
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse_error"}}
        if response:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
