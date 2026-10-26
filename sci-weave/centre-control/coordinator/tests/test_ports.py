"""Port and snapshot contract tests.

These exercise the coordinator's public port surface rather than dispatch
behaviour; dispatch behaviour lives in test_coordinator.py.
"""

import sqlite3
import typing

from coordinator.ports import (
    FormalSnapshot,
    HandoffReadyMessage,
    PrincipalState,
    UnverifiablePrincipalDirectory,
)
from coordinator.service import CoordinatorService
from coordinator.store import CoordinatorStore


def test_formal_snapshot_carries_latest_published_by():
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        latest_published_by="principal-1",
    )
    assert snapshot.latest_published_by == "principal-1"


def test_formal_snapshot_latest_published_by_defaults_to_none():
    snapshot = FormalSnapshot(mapping_domain_id="map-1", formal_revision_id="rev-1")
    assert snapshot.latest_published_by is None


def test_principal_state_distinguishes_absence_from_uncertainty():
    """Three states, not a bool.

    Collapsing UNKNOWN into ABSENT would make an unreachable registry look like
    proof that a principal no longer exists, which suppresses real
    notifications instead of failing open.
    """
    assert PrincipalState.ACTIVE is not PrincipalState.ABSENT
    assert PrincipalState.ABSENT is not PrincipalState.UNKNOWN
    assert PrincipalState.ACTIVE is not PrincipalState.UNKNOWN


def test_unverifiable_directory_admits_it_cannot_tell():
    directory = UnverifiablePrincipalDirectory()
    assert directory.state_of("anyone") is PrincipalState.UNKNOWN
    assert directory.state_of("anyone") is not PrincipalState.ABSENT


class _StubDirectory:
    """Minimal stand-in so the three outcomes are exercised via the port."""

    def __init__(self, known: dict[str, PrincipalState], reachable: bool = True) -> None:
        self._known = known
        self._reachable = reachable

    def state_of(self, principal_id: str) -> PrincipalState:
        if not self._reachable:
            return PrincipalState.UNKNOWN
        return self._known.get(principal_id, PrincipalState.ABSENT)


def test_service_uses_an_injected_directory_when_given_one():
    """The port has to be reachable through the service, not just standalone."""
    connection = sqlite3.connect(":memory:")
    try:
        service = CoordinatorService(
            CoordinatorStore(connection),
            snapshot_port=None,
            publisher=None,
            notifications=None,
            agents=None,
            principals=_StubDirectory({"principal-1": PrincipalState.ACTIVE}),
        )
        assert service.principals.state_of("principal-1") is PrincipalState.ACTIVE
        assert service.principals.state_of("principal-2") is PrincipalState.ABSENT
    finally:
        connection.close()


def test_service_without_a_directory_still_constructs():
    """Existing call sites pass four ports; the fifth must be optional."""
    connection = sqlite3.connect(":memory:")
    try:
        service = CoordinatorService(
            CoordinatorStore(connection),
            snapshot_port=None,
            publisher=None,
            notifications=None,
            agents=None,
        )
        assert service.principals.state_of("anyone") is PrincipalState.UNKNOWN
    finally:
        connection.close()


def test_handoff_ready_message_carries_protocol_payload_fields():
    message = HandoffReadyMessage(
        mapping_domain_id="map-1",
        task_node_id="T1",
        target_node_version_ref="v1",
        target_agent_id="agent-1",
        pending_handoff_id="p-1",
        trigger_revision_id="rev-1",
        upstream_source_refs=(("T0", "v0"),),
        dependency_edge_version_refs=(("e-1", "ev-1"),),
        executor_ref_snapshot=("agent-1", "agent-2"),
    )
    assert message.upstream_source_refs == (("T0", "v0"),)
    assert message.dependency_edge_version_refs == (("e-1", "ev-1"),)
    assert message.executor_ref_snapshot == ("agent-1", "agent-2")


def test_edge_refs_stay_a_sequence_not_a_bare_element():
    """One edge must not degrade to a bare pair.

    tuple[str, str] is also a tuple, so checking the outer origin alone would
    still pass on that shape -- the second argument has to be checked. Read
    from the annotation because a dataclass does not coerce: any assertion on
    a constructed value passes regardless of the declared type.
    """
    hints = typing.get_type_hints(HandoffReadyMessage)
    for field_name in ("upstream_source_refs", "dependency_edge_version_refs"):
        args = typing.get_args(hints[field_name])
        assert typing.get_origin(hints[field_name]) is tuple, field_name
        assert args[1] is Ellipsis, (
            f"{field_name} must be variadic (...,), not a fixed-arity tuple; got {hints[field_name]}"
        )


def test_new_payload_fields_default_to_empty():
    """Existing call sites construct this message with six fields."""
    message = HandoffReadyMessage(
        mapping_domain_id="map-1",
        task_node_id="T1",
        target_node_version_ref="v1",
        target_agent_id="agent-1",
        pending_handoff_id="p-1",
        trigger_revision_id="rev-1",
    )
    assert message.upstream_source_refs == ()
    assert message.dependency_edge_version_refs == ()
    assert message.executor_ref_snapshot == ()


def test_edge_refs_are_declared_as_pairs_not_bare_strings():
    """The annotation is the contract here, and nothing at runtime enforces it.

    A dataclass does not coerce, so constructing one with pairs passes even
    when the annotation says tuple[str, ...]. Asserting on the constructed
    value therefore cannot catch the regression this test exists for; the
    declared type has to be read directly.
    """
    hints = typing.get_type_hints(HandoffReadyMessage)
    inner = typing.get_args(hints["dependency_edge_version_refs"])[0]
    assert typing.get_origin(inner) is tuple, (
        f"dependency_edge_version_refs must carry (logical_id, version_id) pairs, "
        f"got element type {inner}"
    )


def test_source_and_edge_refs_declare_the_same_element_type():
    """Both answer "which versions is this built on"; one shape keeps them comparable.

    docs/data-flow/message-queue.md renders both as arrays of
    {logical_id, version_id}; a flat string for edges would make the two
    fields unreadable by the same code.
    """
    hints = typing.get_type_hints(HandoffReadyMessage)
    source_inner = typing.get_args(hints["upstream_source_refs"])[0]
    edge_inner = typing.get_args(hints["dependency_edge_version_refs"])[0]
    assert source_inner == edge_inner


def test_a_falsy_directory_adapter_is_still_used():
    """`or` would discard a real adapter that happens to be empty.

    A directory backed by a mapping is falsy when the mapping is empty, and an
    empty directory is a normal state -- nobody is registered yet. Falling back
    to "cannot verify" at that moment would make validation silently stop
    working exactly when it has something to say.
    """

    class MappingDirectory:
        def __init__(self, known: dict[str, PrincipalState]) -> None:
            self._known = known

        def __len__(self) -> int:
            return len(self._known)

        def state_of(self, principal_id: str) -> PrincipalState:
            return self._known.get(principal_id, PrincipalState.ABSENT)

    connection = sqlite3.connect(":memory:")
    try:
        adapter = MappingDirectory({})
        assert not adapter, "precondition: this adapter is falsy while empty"

        service = CoordinatorService(
            CoordinatorStore(connection),
            snapshot_port=None,
            publisher=None,
            notifications=None,
            agents=None,
            principals=adapter,
        )
        assert service.principals is adapter
        assert service.principals.state_of("anyone") is PrincipalState.ABSENT
    finally:
        connection.close()
