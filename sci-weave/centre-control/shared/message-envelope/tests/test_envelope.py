import json

import pytest

from message_envelope import (
    PayloadError,
    SchemaVersionError,
    UnknownMessageTypeError,
    SCHEMA_VERSION,
    Envelope,
    EnvelopeFormatError,
    Producer,
    Routing,
    decode,
    encode,
)


def sample(**overrides) -> Envelope:
    values = dict(
        message_id="msg-1",
        message_type="task_completed",
        schema_version=SCHEMA_VERSION,
        dedupe_key="map-1:T1:v1:task_completed",
        occurred_at="2026-10-26T08:00:00Z",
        published_at="2026-10-26T08:00:01Z",
        producer=Producer(service="coordinator", instance_id="c-1"),
        routing=Routing(partition_key="task:T1"),
        payload={"mapping_domain_id": "map-1"},
    )
    values.update(overrides)
    return Envelope(**values)


def test_envelope_round_trips_through_json():
    original = sample()

    restored = decode(encode(original))

    assert restored == original


def test_malformed_json_raises_format_error():
    with pytest.raises(EnvelopeFormatError):
        decode(b"not json at all")


def test_missing_required_field_raises_format_error():
    body = json.loads(encode(sample()).decode("utf-8"))
    del body["dedupe_key"]

    with pytest.raises(EnvelopeFormatError):
        decode(json.dumps(body).encode("utf-8"))


def test_bad_timestamp_raises_format_error():
    with pytest.raises(EnvelopeFormatError):
        decode(encode(sample(occurred_at="yesterday")))


def test_bad_published_at_raises_format_error():
    with pytest.raises(EnvelopeFormatError):
        decode(encode(sample(published_at="2026-10-26 08:00:01")))


def test_unsupported_schema_version_is_distinct_from_format_error():
    with pytest.raises(SchemaVersionError):
        decode(encode(sample(schema_version=SCHEMA_VERSION + 1)))


def test_unknown_message_type_is_distinct_from_format_error():
    with pytest.raises(UnknownMessageTypeError):
        decode(encode(sample(message_type="something_new")))


def test_unknown_payload_fields_are_tolerated_and_survive_a_round_trip():
    original = sample(payload={"mapping_domain_id": "map-1", "future_field": {"nested": [1, 2]}})

    restored = decode(encode(original))

    assert restored.payload["future_field"] == {"nested": [1, 2]}


def test_payload_must_be_an_object():
    with pytest.raises(PayloadError):
        decode(encode(sample(payload=["not", "an", "object"])))


def test_producer_instance_id_is_optional():
    restored = decode(encode(sample(producer=Producer(service="coordinator"))))

    assert restored.producer == Producer(service="coordinator")


def test_routing_target_agent_id_is_optional():
    restored = decode(encode(sample(routing=Routing(partition_key="task:T1"))))

    assert restored.routing == Routing(partition_key="task:T1")


def test_naive_timestamp_is_rejected():
    # A timestamp without a zone cannot be ordered against another, and
    # ordering is the only thing occurred_at/published_at are for.
    with pytest.raises(EnvelopeFormatError):
        decode(encode(sample(occurred_at="2026-10-26T08:00:00")))


def test_boolean_is_not_a_schema_version():
    body = json.loads(encode(sample()).decode("utf-8"))
    body["schema_version"] = True

    with pytest.raises(EnvelopeFormatError):
        decode(json.dumps(body).encode("utf-8"))


def test_non_object_body_is_rejected():
    with pytest.raises(EnvelopeFormatError):
        decode(b"[1, 2, 3]")


def test_non_utf8_bytes_are_rejected():
    with pytest.raises(EnvelopeFormatError):
        decode(b"\xff\xfe{}")


def raw_body(**overrides) -> bytes:
    body = {
        "message_id": "msg-1",
        "message_type": "task_completed",
        "schema_version": 1,
        "dedupe_key": "map-1:T1:v1:task_completed",
        "occurred_at": "2026-10-26T08:00:00Z",
        "published_at": "2026-10-26T08:00:01Z",
        "producer": {"service": "coordinator"},
        "routing": {"partition_key": "task:T1"},
        "payload": {"mapping_domain_id": "map-1"},
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


def test_payload_that_is_not_an_object_is_rejected_on_the_decode_side():
    # encode() validates too, so going through it would test the encoder
    # and leave the consumer's own guard unexercised.
    with pytest.raises(PayloadError):
        decode(raw_body(payload=[1, 2]))


def test_missing_payload_key_is_a_format_error():
    # Every message type has required payload fields, so an envelope that
    # arrives without the key at all is malformed rather than empty. An
    # explicit {} is still a payload and is accepted.
    body = json.loads(raw_body())
    del body["payload"]

    with pytest.raises(EnvelopeFormatError):
        decode(json.dumps(body).encode("utf-8"))


def test_explicit_empty_payload_is_accepted():
    assert decode(raw_body(payload={})).payload == {}
