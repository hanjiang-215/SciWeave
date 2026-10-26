"""SciWeave message envelope: schema, JSON codec and validation.

This package is protocol-only. It holds no Kafka client, opens no
connection, starts no consumer and contains no retry loop. Roles attach
their own client and call into here for construction and validation.

Failures are deliberately split four ways, because a consumer does
something different in each case:

- :class:`EnvelopeFormatError` — the bytes are not a usable envelope.
  Permanent; the producer is broken.
- :class:`SchemaVersionError` — the version is one we do not speak. May
  mean the publisher shipped ahead of us.
- :class:`UnknownMessageTypeError` — a type we have no handler for. May
  mean a new producer went live.
- :class:`PayloadError` — the envelope is fine but the business payload
  is not.

Collapsing these into one error would discard the only signal a consumer
has for deciding whether to drop, upgrade, or route to a human.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1

MESSAGE_TYPES = frozenset(
    {
        "task_handoff_ready",
        "task_completed",
        "formal_revision_published",
        "candidate_created",
        "candidate_head_updated",
    }
)

__all__ = [
    "SCHEMA_VERSION",
    "MESSAGE_TYPES",
    "Envelope",
    "EnvelopeError",
    "EnvelopeFormatError",
    "Producer",
    "PayloadError",
    "Routing",
    "SchemaVersionError",
    "UnknownMessageTypeError",
    "decode",
    "encode",
    "validate",
]


class EnvelopeError(Exception):
    """Base class for every envelope failure; catch this to catch them all."""


class EnvelopeFormatError(EnvelopeError):
    """The bytes are not a well-formed envelope."""


class SchemaVersionError(EnvelopeError):
    """The message declares a schema version this code does not support."""

    def __init__(self, version: Any) -> None:
        super().__init__(f"unsupported schema_version: {version!r}")
        self.version = version


class UnknownMessageTypeError(EnvelopeError):
    """The message type is not one this code knows how to route."""

    def __init__(self, message_type: Any) -> None:
        super().__init__(f"unknown message_type: {message_type!r}")
        self.message_type = message_type


class PayloadError(EnvelopeError):
    """The envelope is valid but the business payload is not."""


@dataclass(frozen=True)
class Producer:
    """Which service published the message, and optionally which instance."""

    service: str
    instance_id: str | None = None


@dataclass(frozen=True)
class Routing:
    """Partition key for ordering, plus the handoff target when there is one."""

    partition_key: str
    target_agent_id: str | None = None


@dataclass(frozen=True)
class Envelope:
    """The envelope every SciWeave business message shares.

    ``occurred_at`` and ``published_at`` stay separate: a compensation
    re-publish keeps the original event time while recording this send.
    Merged into one field, out-of-order delivery becomes unjudgeable.
    """

    message_id: str
    message_type: str
    schema_version: int
    dedupe_key: str
    occurred_at: str
    published_at: str
    producer: Producer
    routing: Routing
    payload: dict[str, Any] = field(default_factory=dict)


def encode(envelope: Envelope) -> bytes:
    """Validate, then serialize the envelope to UTF-8 JSON bytes.

    Validating here means a producer learns about a malformed message at
    the point of construction, not when a consumer chokes on it.
    """
    validate(envelope)
    body: dict[str, Any] = {
        "message_id": envelope.message_id,
        "message_type": envelope.message_type,
        "schema_version": envelope.schema_version,
        "dedupe_key": envelope.dedupe_key,
        "occurred_at": envelope.occurred_at,
        "published_at": envelope.published_at,
        "producer": _producer_to_dict(envelope.producer),
        "routing": _routing_to_dict(envelope.routing),
        "payload": envelope.payload,
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")


def decode(data: bytes) -> Envelope:
    """Deserialize UTF-8 JSON bytes into a validated envelope."""
    try:
        body = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvelopeFormatError(f"body is not UTF-8 JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise EnvelopeFormatError("body must be a JSON object")

    envelope = Envelope(
        message_id=_required_str(body, "message_id"),
        message_type=_required_str(body, "message_type"),
        schema_version=_required_int(body, "schema_version"),
        dedupe_key=_required_str(body, "dedupe_key"),
        occurred_at=_required_str(body, "occurred_at"),
        published_at=_required_str(body, "published_at"),
        producer=_producer_from_value(body, "producer"),
        routing=_routing_from_value(body, "routing"),
        payload=_payload_from_value(body),
    )
    validate(envelope)
    return envelope


def validate(envelope: Envelope) -> None:
    """Check an envelope in memory and raise the specific failure if any.

    Unknown payload fields are not an error. Tolerant reading is the
    contract: same schema version is always consumable, and consumers
    must ignore what they do not recognise. Only the envelope's own
    required fields and the schema version are enforced here.
    """
    for name, value in (
        ("message_id", envelope.message_id),
        ("message_type", envelope.message_type),
        ("dedupe_key", envelope.dedupe_key),
    ):
        if not isinstance(value, str) or not value:
            raise EnvelopeFormatError(f"{name} must be a non-empty string")

    if envelope.schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(envelope.schema_version)

    if envelope.message_type not in MESSAGE_TYPES:
        raise UnknownMessageTypeError(envelope.message_type)

    for name, value in (
        ("occurred_at", envelope.occurred_at),
        ("published_at", envelope.published_at),
    ):
        _require_timestamp(name, value)

    if not isinstance(envelope.producer.service, str) or not envelope.producer.service:
        raise EnvelopeFormatError("producer.service must be a non-empty string")

    if not isinstance(envelope.routing.partition_key, str) or not envelope.routing.partition_key:
        raise EnvelopeFormatError("routing.partition_key must be a non-empty string")

    if not isinstance(envelope.payload, dict):
        raise PayloadError("payload must be a JSON object")


def _require_timestamp(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise EnvelopeFormatError(f"{name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvelopeFormatError(f"{name} is not an ISO-8601 timestamp: {value!r}") from exc
    # A timestamp without a zone cannot be ordered against another one, which
    # is the only thing these two fields are for.
    if parsed.tzinfo is None:
        raise EnvelopeFormatError(f"{name} must carry a timezone: {value!r}")


def _required_str(body: dict[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value:
        raise EnvelopeFormatError(f"{name} must be a non-empty string")
    return value


def _required_int(body: dict[str, Any], name: str) -> int:
    value = body.get(name)
    # bool is an int subclass; `true` is not a schema version.
    if not isinstance(value, int) or isinstance(value, bool):
        raise EnvelopeFormatError(f"{name} must be an integer")
    return value


def _payload_from_value(body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("payload")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PayloadError("payload must be a JSON object")
    return value


def _producer_to_dict(producer: Producer) -> dict[str, Any]:
    body: dict[str, Any] = {"service": producer.service}
    if producer.instance_id is not None:
        body["instance_id"] = producer.instance_id
    return body


def _producer_from_value(body: dict[str, Any], name: str) -> Producer:
    value = body.get(name)
    if not isinstance(value, dict):
        raise EnvelopeFormatError(f"{name} must be a JSON object")
    service = value.get("service")
    if not isinstance(service, str) or not service:
        raise EnvelopeFormatError(f"{name}.service must be a non-empty string")
    instance_id = value.get("instance_id")
    if instance_id is not None and not isinstance(instance_id, str):
        raise EnvelopeFormatError(f"{name}.instance_id must be a string when present")
    return Producer(service=service, instance_id=instance_id)


def _routing_to_dict(routing: Routing) -> dict[str, Any]:
    body: dict[str, Any] = {"partition_key": routing.partition_key}
    if routing.target_agent_id is not None:
        body["target_agent_id"] = routing.target_agent_id
    return body


def _routing_from_value(body: dict[str, Any], name: str) -> Routing:
    value = body.get(name)
    if not isinstance(value, dict):
        raise EnvelopeFormatError(f"{name} must be a JSON object")
    partition_key = value.get("partition_key")
    if not isinstance(partition_key, str) or not partition_key:
        raise EnvelopeFormatError(f"{name}.partition_key must be a non-empty string")
    target_agent_id = value.get("target_agent_id")
    if target_agent_id is not None and not isinstance(target_agent_id, str):
        raise EnvelopeFormatError(f"{name}.target_agent_id must be a string when present")
    return Routing(partition_key=partition_key, target_agent_id=target_agent_id)
