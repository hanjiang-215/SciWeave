from __future__ import annotations

from typing import Any


class BufferError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def call_tool(service: "DraftBufferService", name: str, arguments: dict[str, Any]):
    handlers = {
        "create_draft": service.create_draft,
        "update_draft": service.update_draft,
        "submit_draft": service.submit_draft,
        "list_drafts": service.list_drafts,
        "read_draft": service.read_draft,
        "review_draft": service.review_draft,
        "mark_promoted": service.mark_promoted,
    }
    handler = handlers.get(name)
    if handler is None:
        raise BufferError("unknown_tool", f"Unknown tool: {name}")
    return handler(**arguments)
