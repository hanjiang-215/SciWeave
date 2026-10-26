"""Per-message-type payload rules: what a payload must carry.

The envelope module answers "is this a usable envelope"; this module
answers "does this payload make sense for this message type". Both are
protocol-level checks, but they fail differently: an envelope defect is a
broken producer, a payload defect is a producer bug that happens to sit one
level down, and a consumer may well want to route those two apart.

Only *presence* and the *shape of the multi-valued refs* are enforced. The
tolerant-reading rule from the protocol still holds: an unknown extra field
is never an error, because the consumer must ignore what it does not
recognise. Strictness applies to missing required fields, not to surplus
ones.

Nothing here validates the *content* of a field. Whether a
`mapping_domain_id` names a domain that exists is the receiving service's
question; a protocol package that asked it would need the domain's
database.
"""

from __future__ import annotations

from typing import Any

from .errors import PayloadError

#: Required payload fields per message type. Field names and their required
#: status come from `ai4-te1v`'s unified envelope table; do not add or drop
#: entries here without changing that decision first.
PAYLOAD_SCHEMAS: dict[str, tuple[str, ...]] = {
    "task_handoff_ready": (
        "mapping_domain_id",
        "task_node_id",
        "target_node_version_ref",
        "target_agent_id",
        "pending_handoff_id",
        "trigger_revision_id",
        "upstream_source_refs",
        "dependency_edge_version_refs",
        "executor_ref_snapshot",
    ),
    "task_completed": (
        "mapping_domain_id",
        "task_node_id",
        "completed_version_ref",
        "execution_id",
        "draft_id",
        "completed_at",
        "result_ref",
    ),
    "formal_revision_published": (
        "mapping_domain_id",
        "formal_revision_id",
    ),
    "candidate_created": (
        "mapping_domain_id",
        "candidate_id",
    ),
    "candidate_head_updated": (
        "mapping_domain_id",
        "candidate_id",
    ),
}

#: Fields that are always arrays, even when they hold a single element.
#:
#: A shape that changes with the number of edges forces every consumer to
#: write two branches, and the branch that handles "one" is the one nobody
#: tests. `executor_ref_snapshot` is here for the same reason: it records the
#: whole executor set seen at dispatch time, and that set is compared against
#: what the formal Map says later.
ARRAY_FIELDS: dict[str, tuple[str, ...]] = {
    "task_handoff_ready": (
        "upstream_source_refs",
        "dependency_edge_version_refs",
        "executor_ref_snapshot",
    ),
}


def required_payload_fields(message_type: str) -> tuple[str, ...]:
    """Required payload fields for a message type, or () if it has none.

    An unknown type is not an error here: the envelope's `validate` already
    rejects it with `UnknownMessageTypeError`, and raising a second error
    kind for the same fact would give consumers two ways to learn it.
    """
    return PAYLOAD_SCHEMAS.get(message_type, ())


def validate_payload(message_type: str, payload: dict[str, Any]) -> None:
    """Raise :class:`PayloadError` if the payload breaks the type's rules."""
    # JSON object keys are strings, so a non-string key would be silently
    # rewritten on the wire and could never be matched back by the producer.
    # It also breaks deterministic serialisation (sorted keys cannot compare
    # an int with a str), which is the only reason the failure is caught at
    # all -- say what is wrong instead of leaking a TypeError from json.
    non_string_keys = [key for key in payload if not isinstance(key, str)]
    if non_string_keys:
        raise PayloadError(
            f"{message_type} payload keys must be strings, got {non_string_keys[0]!r}"
        )

    missing = [
        name
        for name in required_payload_fields(message_type)
        if name not in payload or payload[name] is None
    ]
    if missing:
        raise PayloadError(
            f"{message_type} payload is missing required field(s): {', '.join(missing)}"
        )

    for name in ARRAY_FIELDS.get(message_type, ()):
        if name in payload and not isinstance(payload[name], list):
            # A single ref written as a scalar is the shape change this rule
            # exists to stop; naming the type makes the fix obvious.
            raise PayloadError(
                f"{message_type} payload field {name!r} must be an array, "
                f"got {type(payload[name]).__name__}"
            )
