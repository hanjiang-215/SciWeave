"""Port and snapshot contract tests.

These exercise the coordinator's public port surface rather than dispatch
behaviour; dispatch behaviour lives in test_coordinator.py.
"""

import sqlite3

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


def test_directory_port_reports_all_three_outcomes():
    """Each state must be reachable, and each means something different."""
    directory = _StubDirectory({"principal-1": PrincipalState.ACTIVE})
    assert directory.state_of("principal-1") is PrincipalState.ACTIVE
    assert directory.state_of("principal-2") is PrincipalState.ABSENT

    unreachable = _StubDirectory({"principal-1": PrincipalState.ACTIVE}, reachable=False)
    assert unreachable.state_of("principal-1") is PrincipalState.UNKNOWN


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
        dependency_edge_version_refs=("e-1",),
        executor_ref_snapshot=("agent-1", "agent-2"),
    )
    assert message.upstream_source_refs == (("T0", "v0"),)
    assert message.dependency_edge_version_refs == ("e-1",)
    assert message.executor_ref_snapshot == ("agent-1", "agent-2")


def test_dependency_edge_version_refs_stays_a_sequence_with_one_element():
    """One edge must not degrade to a bare string.

    A shape that changes with cardinality forces every consumer to branch on
    length before it can iterate.
    """
    message = HandoffReadyMessage(
        mapping_domain_id="map-1",
        task_node_id="T1",
        target_node_version_ref="v1",
        target_agent_id="agent-1",
        pending_handoff_id="p-1",
        trigger_revision_id="rev-1",
        dependency_edge_version_refs=("e-only",),
    )
    assert isinstance(message.dependency_edge_version_refs, tuple)
    assert message.dependency_edge_version_refs == ("e-only",)


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
