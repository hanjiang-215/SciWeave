import json

import pytest

from message_envelope import (
    MESSAGE_TYPES,
    SCHEMA_VERSION,
    Envelope,
    EnvelopeError,
    EnvelopeFormatError,
    PayloadError,
    Producer,
    Routing,
    SchemaVersionError,
    UnknownMessageTypeError,
    decode,
    encode,
    validate,
)


def sample(**overrides) -> Envelope:
    values = dict(
        message_id="msg-1",
        message_type="task_completed",
        schema_version=SCHEMA_VERSION,
        dedupe_key="map-1:T1:v1:task_completed",
        occurred_at="2026-10-26T08:00:00Z",
        published_at="2026-10-26T08:00:01Z",
        producer=Producer(service="coordinator"),
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
    # Decode from bytes we did not produce. Going through encode() would
    # raise inside encode's own validate() and leave the consumer's guard
    # untested.
    with pytest.raises(SchemaVersionError):
        decode(raw_body(schema_version=SCHEMA_VERSION + 1))


def test_unknown_message_type_is_distinct_from_format_error():
    with pytest.raises(UnknownMessageTypeError):
        decode(raw_body(message_type="something_new"))


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


def test_routing_target_agent_id_survives_a_round_trip():
    # task_handoff_ready must name the agent it is routed to; if the
    # serialiser drops this, the handoff silently lands nowhere.
    original = sample(
        message_type="task_handoff_ready",
        routing=Routing(partition_key="task:T1", target_agent_id="agent-7"),
    )

    restored = decode(encode(original))

    assert restored.routing.target_agent_id == "agent-7"


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"message_id": ""}, id="empty-message_id"),
        pytest.param({"message_id": 7}, id="non-string-message_id"),
        pytest.param({"dedupe_key": ""}, id="empty-dedupe_key"),
        pytest.param({"producer": "coordinator"}, id="producer-is-a-string"),
        pytest.param({"producer": {"service": ""}}, id="empty-producer-service"),
        pytest.param({"producer": {"service": 1}}, id="non-string-producer-service"),
        pytest.param({"producer": {"service": "c", "instance_id": 2}}, id="non-string-instance_id"),
        pytest.param({"routing": "task:T1"}, id="routing-is-a-string"),
        pytest.param({"routing": {"partition_key": ""}}, id="empty-partition_key"),
        pytest.param({"routing": {"partition_key": "k", "target_agent_id": 3}}, id="non-string-target_agent_id"),
        pytest.param({"schema_version": "1"}, id="string-schema_version"),
    ],
)
def test_structurally_malformed_envelope_is_a_format_error(override):
    # These arrive from a topic, so they are untrusted input rather than a
    # programming mistake: a producer on an older build, or a hand-edited
    # message. Each must fail as a format error, not crash with TypeError.
    with pytest.raises(EnvelopeFormatError):
        decode(raw_body(**override))


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"message_id": ""}, id="empty-message_id"),
        pytest.param({"dedupe_key": ""}, id="empty-dedupe_key"),
        pytest.param({"producer": Producer(service="")}, id="empty-producer-service"),
        pytest.param({"routing": Routing(partition_key="")}, id="empty-partition_key"),
    ],
)
def test_validate_rejects_blank_fields_on_a_hand_built_envelope(override):
    # encode() runs validate(), so a producer that builds an Envelope in
    # memory gets stopped here rather than publishing a message the
    # consumer would reject.
    with pytest.raises(EnvelopeFormatError):
        encode(sample(**override))


@pytest.mark.parametrize("field", ["occurred_at", "published_at"])
def test_validate_rejects_a_missing_timestamp(field):
    # decode() catches a blank timestamp as a missing string first; this
    # covers the same guard on a hand-built envelope that skipped decode.
    with pytest.raises(EnvelopeFormatError):
        encode(sample(**{field: ""}))


def test_message_catalogue_is_exactly_the_five_redpanda_types():
    # human_notification_intent and task_terminal_summary travel over MCP,
    # not Redpanda. Pinning the set keeps that boundary from drifting.
    assert MESSAGE_TYPES == {
        "task_handoff_ready",
        "task_completed",
        "formal_revision_published",
        "candidate_created",
        "candidate_head_updated",
    }


def test_payload_error_is_not_an_envelope_format_error():
    # Collapsing these two would still satisfy every pytest.raises above,
    # because a subclass passes an isinstance check. The four-way split is
    # only real if the classes stay siblings.
    assert not issubclass(PayloadError, EnvelopeFormatError)
    assert not issubclass(EnvelopeFormatError, PayloadError)


def test_encode_refuses_what_decode_would_reject():
    # A producer that hands us a bool or a float schema version would get
    # bytes back and only find out when its consumer rejects them.
    for bad in (True, 1.0, "1"):
        with pytest.raises(EnvelopeFormatError):
            encode(sample(schema_version=bad))


def test_encode_refuses_a_non_string_instance_id():
    with pytest.raises(EnvelopeFormatError):
        encode(sample(producer=Producer(service="coordinator", instance_id=2)))


def test_encode_refuses_a_non_string_target_agent_id():
    with pytest.raises(EnvelopeFormatError):
        encode(sample(routing=Routing(partition_key="task:T1", target_agent_id=3)))


def test_validate_reports_missing_producer_and_routing_as_format_errors():
    # Untrusted input can leave these None; an AttributeError escaping the
    # validator tells the caller nothing about what was wrong.
    for override in ({"producer": None}, {"routing": None}):
        with pytest.raises(EnvelopeFormatError):
            encode(sample(**override))


def test_decode_rejects_a_str_argument():
    # Callers hand us bytes from a client, but a str that slipped through
    # (e.g. from a JSON fixture) should read as a format error.
    with pytest.raises(EnvelopeFormatError):
        decode('{"message_id": "m"}')


def test_envelope_requires_an_explicit_payload():
    # Without this, the package can build the empty-payload envelope its own
    # decoder rejects, which makes "an absent payload is malformed" a rule
    # only outsiders have to follow.
    with pytest.raises(TypeError):
        Envelope(
            message_id="m",
            message_type="task_completed",
            schema_version=SCHEMA_VERSION,
            dedupe_key="d",
            occurred_at="2026-10-26T08:00:00Z",
            published_at="2026-10-26T08:00:01Z",
            producer=Producer(service="coordinator"),
            routing=Routing(partition_key="task:T1"),
        )


def test_unserialisable_payload_is_a_payload_error_not_a_type_error():
    # The README promises EnvelopeError catches everything this package
    # raises; a bare TypeError from json.dumps would break that.
    with pytest.raises(PayloadError):
        encode(sample(payload={"when": object()}))


def test_nan_payload_is_refused_rather_than_written_as_invalid_json():
    # NaN is Python's json extension, not JSON. Writing it produces a
    # message a non-Python consumer cannot parse.
    with pytest.raises(PayloadError):
        encode(sample(payload={"n": float("nan")}))


def test_non_string_payload_keys_become_strings_on_the_wire():
    # JSON object keys are strings, so this conversion is unavoidable rather
    # than a bug. Pinning it makes it a documented property instead of a
    # surprise: a payload keyed by an int comes back keyed by "1".
    restored = decode(encode(sample(payload={1: "a"})))

    assert restored.payload == {"1": "a"}


def test_structural_defects_outrank_the_version_check():
    # A consumer that keys its upgrade prompt off SchemaVersionError needs to
    # know it will not always get one: a v2 message that is also missing a
    # required field reports the field. Pinning it keeps that documented
    # precedence from drifting silently.
    with pytest.raises(EnvelopeFormatError):
        decode(raw_body(schema_version=SCHEMA_VERSION + 1, dedupe_key=""))


def test_timestamps_must_use_the_extended_form_with_a_t_separator():
    # fromisoformat on 3.11+ also accepts "2026-10-26X08:00:01Z" and the
    # compact "20261026T080001Z". Permitting them means our own producers can
    # emit bytes a stricter consumer elsewhere rejects, so the wire format is
    # pinned to the extended form here instead of inheriting the parser's tastes.
    for malformed in (
        "2026-10-26X08:00:01Z",
        "20261026T080001Z",
        "2026-10-26 08:00:01+00:00",
        # Has the T, but is not a date: the format guard lets it through and
        # the parser has to reject it.
        "2026-10-26THELLO!!!",
    ):
        with pytest.raises(EnvelopeFormatError):
            encode(sample(occurred_at=malformed))


def test_every_leaf_exception_is_caught_by_the_base_class():
    # The README tells consumers to catch EnvelopeError for a single handler.
    # That only works if every leaf actually descends from it.
    for leaf in (EnvelopeFormatError, SchemaVersionError, UnknownMessageTypeError, PayloadError):
        assert issubclass(leaf, EnvelopeError)


def test_catching_the_base_class_catches_every_failure_this_package_raises():
    # The behavioural version of the claim above: one handler, four failures.
    def swallow(fn) -> type:
        try:
            fn()
        except EnvelopeError as exc:
            return type(exc)
        raise AssertionError("no EnvelopeError raised")

    assert swallow(lambda: decode(b"not json")) is EnvelopeFormatError
    assert swallow(lambda: decode(raw_body(schema_version=2))) is SchemaVersionError
    assert swallow(lambda: decode(raw_body(message_type="unknown"))) is UnknownMessageTypeError
    assert swallow(lambda: encode(sample(payload={"x": object()}))) is PayloadError
    assert swallow(lambda: validate(sample(occurred_at=""))) is EnvelopeFormatError


def test_absent_optional_fields_are_omitted_not_written_as_null():
    # The wire format has no nulls. Writing "target_agent_id": null would force
    # every consumer to treat absent and null as the same thing, and a consumer
    # that does not would read a null as a real target.
    body = json.loads(encode(sample()))

    assert "instance_id" not in body["producer"]
    assert "target_agent_id" not in body["routing"]


def test_present_optional_fields_are_written():
    body = json.loads(
        encode(
            sample(
                producer=Producer(service="coordinator", instance_id="c-1"),
                routing=Routing(partition_key="task:T1", target_agent_id="agent-7"),
            )
        )
    )

    assert body["producer"]["instance_id"] == "c-1"
    assert body["routing"]["target_agent_id"] == "agent-7"


def test_validate_rejects_a_non_object_payload_directly():
    # decode() has its own shape guard, so a hole in validate() alone would
    # only show up for in-process producers that call validate themselves.
    with pytest.raises(PayloadError):
        validate(sample(payload=["not", "an", "object"]))
