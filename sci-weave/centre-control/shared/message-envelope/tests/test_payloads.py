"""Payload rules per message type (ai4-sv1u).

These tests are the reason the payload schema exists: a producer that
forgets a field should fail here, at construction, not in a consumer's
parser three hops away. The payload literals are written out in full rather
than generated from `PAYLOAD_SCHEMAS`, because a fixture derived from the
schema would keep passing if someone deleted a field from the schema.
"""

import json

import pytest

from message_envelope import (
    SCHEMA_VERSION,
    Envelope,
    EnvelopeFormatError,
    PayloadError,
    Producer,
    Routing,
    SchemaVersionError,
    UnknownMessageTypeError,
    decode,
    encode,
    required_payload_fields,
    validate,
    validate_payload,
)

#: One complete payload per message type. Kept as literals: they are the
#: contract copied from `ai4-te1v`, not a mirror of the implementation.
PAYLOADS = {
    "task_handoff_ready": {
        "mapping_domain_id": "map-1",
        "task_node_id": "T1",
        "target_node_version_ref": "v1",
        "target_agent_id": "agent-7",
        "pending_handoff_id": "ph-1",
        "trigger_revision_id": "rev-1",
        "upstream_source_refs": ["rev-0"],
        "dependency_edge_version_refs": ["edge-v1"],
        "executor_ref_snapshot": ["agent-7"],
    },
    "task_completed": {
        "mapping_domain_id": "map-1",
        "task_node_id": "T1",
        "completed_version_ref": "v1",
        "execution_id": "exec-1",
        "draft_id": "draft-1",
        "completed_at": "2026-10-26T08:00:00Z",
        "result_ref": "result-1",
    },
    "formal_revision_published": {
        "mapping_domain_id": "map-1",
        "formal_revision_id": "rev-1",
    },
    "candidate_created": {
        "mapping_domain_id": "map-1",
        "candidate_id": "cand-1",
    },
    "candidate_head_updated": {
        "mapping_domain_id": "map-1",
        "candidate_id": "cand-1",
    },
}

ARRAY_FIELDS = ("upstream_source_refs", "dependency_edge_version_refs", "executor_ref_snapshot")


def envelope_for(message_type: str, payload: dict) -> Envelope:
    return Envelope(
        message_id="msg-1",
        message_type=message_type,
        schema_version=SCHEMA_VERSION,
        dedupe_key=f"map-1:T1:v1:{message_type}",
        occurred_at="2026-10-26T08:00:00Z",
        published_at="2026-10-26T08:00:01Z",
        producer=Producer(service="coordinator"),
        routing=Routing(partition_key="task:T1"),
        payload=payload,
    )


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_every_message_type_round_trips_with_its_required_payload(message_type):
    original = envelope_for(message_type, dict(PAYLOADS[message_type]))

    restored = decode(encode(original))

    assert restored.payload == PAYLOADS[message_type]


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_each_message_type_rejects_a_missing_required_field(message_type):
    for field in PAYLOADS[message_type]:
        incomplete = dict(PAYLOADS[message_type])
        del incomplete[field]

        with pytest.raises(PayloadError):
            encode(envelope_for(message_type, incomplete))


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_each_message_type_tolerates_an_unknown_field(message_type):
    # Tolerant reading survives payload typing: strictness is about missing
    # required fields, not about surplus ones.
    payload = dict(PAYLOADS[message_type], field_from_the_future={"nested": [1, 2]})

    restored = decode(encode(envelope_for(message_type, payload)))

    assert restored.payload["field_from_the_future"] == {"nested": [1, 2]}


@pytest.mark.parametrize("field", ARRAY_FIELDS)
def test_a_single_element_ref_stays_an_array(field):
    # The shape must not depend on the number of edges: a consumer that has
    # to branch on "one or many" will get the "one" branch wrong.
    payload = dict(PAYLOADS["task_handoff_ready"], **{field: ["only-one"]})

    restored = decode(encode(envelope_for("task_handoff_ready", payload)))

    assert restored.payload[field] == ["only-one"]
    assert isinstance(restored.payload[field], list)


@pytest.mark.parametrize("field", ARRAY_FIELDS)
def test_a_scalar_ref_is_rejected(field):
    payload = dict(PAYLOADS["task_handoff_ready"], **{field: "only-one"})

    with pytest.raises(PayloadError):
        encode(envelope_for("task_handoff_ready", payload))


def test_executor_ref_snapshot_carries_several_executors():
    # The snapshot exists to answer "did we pick the wrong executor, or was
    # there only one?" after the fact, so more than one ref must fit.
    payload = dict(PAYLOADS["task_handoff_ready"], executor_ref_snapshot=["agent-7", "agent-8"])

    restored = decode(encode(envelope_for("task_handoff_ready", payload)))

    assert restored.payload["executor_ref_snapshot"] == ["agent-7", "agent-8"]


def test_missing_payload_field_is_a_payload_error_not_a_format_error():
    # A consumer decides what to do from the exception kind: format means a
    # broken producer, payload means a bug in a producer we can name. A
    # subclass check would pass either way, so compare the classes.
    payload = dict(PAYLOADS["task_completed"])
    del payload["draft_id"]

    with pytest.raises(PayloadError) as raised:
        validate(envelope_for("task_completed", payload))

    assert type(raised.value) is PayloadError
    assert not isinstance(raised.value, EnvelopeFormatError)


def test_payload_rules_do_not_mask_the_version_error():
    # The envelope's own defects are decided before the payload's, so a v2
    # message with an empty payload still reports as a version problem. A
    # consumer that keys its upgrade prompt off SchemaVersionError relies on
    # this order.
    body = json.dumps(
        {
            "message_id": "m",
            "message_type": "task_completed",
            "schema_version": SCHEMA_VERSION + 1,
            "dedupe_key": "d",
            "occurred_at": "2026-10-26T08:00:00Z",
            "published_at": "2026-10-26T08:00:01Z",
            "producer": {"service": "coordinator"},
            "routing": {"partition_key": "task:T1"},
            "payload": {},
        }
    ).encode("utf-8")

    with pytest.raises(SchemaVersionError):
        decode(body)


def test_unknown_message_type_is_reported_before_its_payload():
    with pytest.raises(UnknownMessageTypeError):
        validate(
            Envelope(
                message_id="m",
                message_type="something_new",
                schema_version=SCHEMA_VERSION,
                dedupe_key="d",
                occurred_at="2026-10-26T08:00:00Z",
                published_at="2026-10-26T08:00:01Z",
                producer=Producer(service="coordinator"),
                routing=Routing(partition_key="task:T1"),
                payload={},
            )
        )


def test_required_fields_are_published_per_message_type():
    # Callers that build payloads programmatically read the same list the
    # validator enforces, so the two cannot drift.
    assert required_payload_fields("task_handoff_ready") == (
        "mapping_domain_id",
        "task_node_id",
        "target_node_version_ref",
        "target_agent_id",
        "pending_handoff_id",
        "trigger_revision_id",
        "upstream_source_refs",
        "dependency_edge_version_refs",
        "executor_ref_snapshot",
    )


def test_an_unknown_message_type_has_no_payload_rules():
    # The envelope validator already rejects unknown types; returning an
    # empty tuple keeps this helper from inventing a second error kind.
    assert required_payload_fields("something_new") == ()


def test_a_null_required_field_counts_as_missing():
    # A producer that writes None usually means "I forgot to fill this in".
    # Accepting it would push the failure into the consumer's own code.
    payload = dict(PAYLOADS["candidate_created"], candidate_id=None)

    with pytest.raises(PayloadError):
        validate_payload("candidate_created", payload)
