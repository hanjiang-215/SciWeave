"""审计事件模型与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ActorType:
    """actor_type 的合法取值。"""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"

    ALL = frozenset({HUMAN, AGENT, SYSTEM})


class Operation:
    """operation 的事件类型枚举（首版 5 个）。"""

    DRAFT_STATUS_CHANGED = "draft.status_changed"
    MAPPING_PREREVIEW_LOG_APPENDED = "mapping.prereview_log_appended"
    MAPPING_FORMAL_REVISION_PROMOTED = "mapping.formal_revision_promoted"
    WIKI_PREREVIEW_LOG_APPENDED = "wiki.prereview_log_appended"
    WIKI_FORMAL_REVISION_PROMOTED = "wiki.formal_revision_promoted"

    ALL = frozenset(
        {
            DRAFT_STATUS_CHANGED,
            MAPPING_PREREVIEW_LOG_APPENDED,
            MAPPING_FORMAL_REVISION_PROMOTED,
            WIKI_PREREVIEW_LOG_APPENDED,
            WIKI_FORMAL_REVISION_PROMOTED,
        }
    )


class AuditValidationError(ValueError):
    """审计事件字段缺失或枚举非法。"""


class TransactionRequiredError(ValueError):
    """写审计事件时连接不在事务内。"""


@dataclass
class AuditEvent:
    """一条追加式审计事件。

    必填字段缺一不可；``event_id`` 与 ``occurred_at`` 由写入函数生成，
    调用方不传。弱引用字段按事件类型选填，``refs`` 兜底放其他关联。
    """

    actor_id: str
    actor_type: str
    operation: str
    target_object_type: str
    target_object_id: str
    result: str

    previous_state: str | None = None
    next_state: str | None = None
    reason: str | None = None
    base_revision: str | None = None
    candidate_revision: str | None = None
    proposal_id: str | None = None
    task_id: str | None = None
    resource_id: str | None = None
    formal_revision_id: str | None = None
    merge_request_id: str | None = None
    refs: dict[str, Any] | None = None

    _required = (
        "actor_id",
        "actor_type",
        "operation",
        "target_object_type",
        "target_object_id",
        "result",
    )

    def validate(self) -> None:
        """校验必填字段与枚举，非法即抛 :class:`AuditValidationError`。"""
        for name in self._required:
            value = getattr(self, name)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise AuditValidationError(f"missing required field: {name}")

        if self.actor_type not in ActorType.ALL:
            raise AuditValidationError(
                f"invalid actor_type {self.actor_type!r}; expected one of {sorted(ActorType.ALL)}"
            )
        if self.operation not in Operation.ALL:
            raise AuditValidationError(
                f"invalid operation {self.operation!r}; expected one of {sorted(Operation.ALL)}"
            )
