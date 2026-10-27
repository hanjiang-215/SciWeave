"""The notification a finished draft sends, and the four rules it must satisfy.

The agent sends the notification through the `email-service` MCP card — it is the
one that knows *who* the owner is, because it read `task_owner_id` from the
mapping. But three of the eight required fields are pure runtime bookkeeping and
must not be left to a model:

- ``dedupe_key`` — derived from the execution id, so a replayed handoff sends one
  notification rather than two;
- ``related`` — must carry ``execution_id`` / ``task_node_id`` so a human can get
  back to the run that produced the draft;
- ``schema_version`` — must be the *string* ``"1"``; an integer is rejected by the
  service (``intent.get("schema_version") != "1"``).

This module builds that fixed part, renders it into the final writer's prompt, and
pre-flights the result. The service remains authoritative: the checks here exist
so a researcher sees "subject is 240 characters" instead of an opaque
``invalid`` from a remote server, not to replace the server's validation.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
#: The only notification kind this kit uses. `CONFIGURED_NOTIFICATION_KINDS` in
#: `centre-control/email-service/src/email_service/service.py` is a closed set of
#: 13 and does not contain anything like `task_agent_run_finished`; `draft_ready`
#: is the one whose meaning matches "a draft is waiting for review".
NOTIFICATION_KIND = "draft_ready"

#: A string, not the integer 1. The service compares against `"1"`.
SCHEMA_VERSION = "1"

#: Limits enforced by `_content_problem` in the email-service.
SUBJECT_MAX_CHARS = 200
BODY_MAX_CHARS = 4000

#: Same shape the service rejects: HTML markup is not allowed in either field.
_HTML_MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>|<!--|-->")

#: C0 controls except tab and newline, plus DEL — the service rejects these.
_DISALLOWED_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class NotificationIntent:
    """The eight fields `send_notification` requires."""

    notification_id: str
    dedupe_key: str
    notification_kind: str
    recipients: tuple[dict, ...]
    subject: str
    body: str
    related: dict
    schema_version: str

    def to_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "dedupe_key": self.dedupe_key,
            "notification_kind": self.notification_kind,
            "recipients": list(self.recipients),
            "subject": self.subject,
            "body": self.body,
            "related": dict(self.related),
            "schema_version": self.schema_version,
        }


def dedupe_key(execution_id: str) -> str:
    """The key a replayed handoff collides with, so the owner is mailed once."""
    return f"draft-ready:{execution_id}"


def build_intent(
    *,
    execution_id: str,
    task_node_id: str,
    recipient_principal_id: str,
    subject: str,
    body: str,
    notification_id: str | None = None,
) -> NotificationIntent:
    """Assemble an intent with the runtime-owned fields already filled in."""
    return NotificationIntent(
        notification_id=notification_id or str(uuid.uuid4()),
        dedupe_key=dedupe_key(execution_id),
        notification_kind=NOTIFICATION_KIND,
        recipients=({"principal_id": recipient_principal_id},),
        subject=subject,
        body=body,
        related={"execution_id": execution_id, "task_node_id": task_node_id},
        schema_version=SCHEMA_VERSION,
    )


def notification_problem(intent: NotificationIntent | dict) -> str | None:
    """The first rule the intent breaks, named; ``None`` when it looks sendable.

    Mirrors `_content_problem` so a mistake surfaces locally with a specific
    code. The remote `invalid` code stays the truth: the service may grow a rule
    this does not know, and nothing here may be used to *skip* calling it.
    """
    data = intent.to_dict() if isinstance(intent, NotificationIntent) else intent
    if not str(data.get("dedupe_key") or "").strip():
        return "dedupe_key_empty"
    if data.get("notification_kind") != NOTIFICATION_KIND:
        return "notification_kind_unexpected"
    if data.get("schema_version") != SCHEMA_VERSION:
        return "schema_version_not_string_1"
    if not isinstance(data.get("related"), dict):
        return "related_not_an_object"
    recipients = data.get("recipients")
    if not isinstance(recipients, list) or not recipients:
        return "recipients_empty"
    for recipient in recipients:
        if not isinstance(recipient, dict) or not str(recipient.get("principal_id") or "").strip():
            return "recipient_without_principal_id"
    subject = str(data.get("subject") or "")
    body = str(data.get("body") or "")
    if not subject.strip() or not body.strip():
        return "empty_subject_or_body"
    if _HTML_MARKUP.search(subject) or _HTML_MARKUP.search(body):
        return "html_not_allowed"
    if _DISALLOWED_CONTROL.search(subject) or _DISALLOWED_CONTROL.search(body):
        return "control_character_not_allowed"
    if len(subject) > SUBJECT_MAX_CHARS:
        return "subject_too_long"
    if len(body) > BODY_MAX_CHARS:
        return "body_too_long"
    return None


def notification_brief(*, execution_id: str, task_node_id: str) -> str:
    """The block appended to the final writer's prompt.

    Only the parts the runtime owns are spelled out exactly. Subject, body and
    the owner are the agent's to fill, because they come from what it actually
    read — a runtime that invented them would notify a human about a draft it
    never saw.
    """
    example = {
        "notification_id": "<uuid4>",
        "dedupe_key": dedupe_key(execution_id),
        "notification_kind": NOTIFICATION_KIND,
        "recipients": [{"principal_id": "<映射里读到的 task_owner_id>"}],
        "subject": "<=200 字符，无 HTML",
        "body": "<=4000 字符，无 HTML",
        "related": {"execution_id": execution_id, "task_node_id": task_node_id},
        "schema_version": SCHEMA_VERSION,
    }
    return (
        "草稿写成后，用 email-service 的 send_notification 通知任务负责人。\n"
        "下面这些字段由 runtime 给定，原样传，不要改写或省略：\n"
        f"{json.dumps(example, ensure_ascii=False, indent=2)}\n"
        "recipients 里的 principal_id 用映射读取结果中该节点的 task_owner_id。\n"
        "subject / body 用纯文本，不要写 HTML 标签或控制字符。\n"
        "通知失败时把错误码放进回答的 notification_error 字段，不要重试，\n"
        "也不要让整轮执行失败——草稿已经写成，丢掉它比少发一封邮件更糟。"
    )

__all__ = [
    "BODY_MAX_CHARS",
    "NOTIFICATION_KIND",
    "NotificationIntent",
    "SCHEMA_VERSION",
    "SUBJECT_MAX_CHARS",
    "build_intent",
    "dedupe_key",
    "notification_brief",
    "notification_problem",
]
