from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class SnapshotUnavailableError(Exception):
    """The formal mapping could not be read; caller should back off and retry."""

    def __init__(self, reason: str = "unavailable") -> None:
        super().__init__(reason)
        self.reason = reason


class SnapshotInconsistentError(Exception):
    """The formal mapping exists but its data is inconsistent; do not dispatch."""

    def __init__(self, reason: str = "inconsistent") -> None:
        super().__init__(reason)
        self.reason = reason


class NoSuchRevisionError(Exception):
    """The requested formal revision does not exist; treat as unrecoverable."""

    def __init__(self, reason: str = "no_such_revision") -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TaskNodeDoc:
    task_node_id: str
    version_id: str
    executor_refs: tuple[str, ...] = ()
    task_owner_id: str | None = None


@dataclass(frozen=True)
class DependencyEdgeDoc:
    """One dependency edge from a formal mapping snapshot.

    ``logical_id`` is the edge's stable identity and ``version_id`` its
    immutable version (ai4-fu4i); both come straight from the domain
    DependencyEdge document. The four judgement fields were added whole
    (ai4-quvy): coordinator must not treat every edge as "all upstream
    complete means go" (ai4-te1v dependency-kind rules).
    """

    logical_id: str
    version_id: str
    source_node_id: str
    source_version_id: str
    target_node_id: str
    target_version_id: str
    dependency_kind: str = "information"
    activation_condition: str | None = None
    required_outputs: tuple[str, ...] = ()
    blocks_until: str | None = None
    alternative_group_id: str | None = None


@dataclass(frozen=True)
class FormalSnapshot:
    """A version-consistent minimal dependency graph from get_formal_mapping_at_revision."""

    mapping_domain_id: str
    formal_revision_id: str
    nodes: tuple[TaskNodeDoc, ...] = ()
    edges: tuple[DependencyEdgeDoc, ...] = ()
    # Who approved this revision most recently, not who was appointed project
    # owner: after A approves r1 and B approves r2 the answer is B. Outwardly
    # this still means "notify the project owner".
    # See docs/adr/0004-po-recipient-from-latest-approver.md.
    latest_published_by: str | None = None

    def node_by_id(self, task_node_id: str) -> TaskNodeDoc | None:
        for node in self.nodes:
            if node.task_node_id == task_node_id:
                return node
        return None

    def incoming_edges(self, task_node_id: str) -> tuple[DependencyEdgeDoc, ...]:
        return tuple(edge for edge in self.edges if edge.target_node_id == task_node_id)

    def outgoing_edges(self, task_node_id: str) -> tuple[DependencyEdgeDoc, ...]:
        return tuple(edge for edge in self.edges if edge.source_node_id == task_node_id)


class FormalSnapshotPort(Protocol):
    """Query port for version-consistent formal mapping snapshots."""

    def get_formal_mapping_at_revision(
        self, mapping_domain_id: str, formal_revision_id: str
    ) -> FormalSnapshot:
        """Return the snapshot for the given revision, or raise a snapshot error."""


@dataclass(frozen=True)
class HandoffReadyMessage:
    mapping_domain_id: str
    task_node_id: str
    target_node_version_ref: str
    target_agent_id: str
    pending_handoff_id: str
    trigger_revision_id: str
    # Both ref fields answer "which formal versions is this handoff built on",
    # as (logical_id, version_id) pairs, and stay sequences even at one element
    # so consumers never branch on cardinality. executor_ref_snapshot is audit
    # only: who was visible at dispatch time, never a substitute for checking
    # the current formal map.
    upstream_source_refs: tuple[tuple[str, str], ...] = ()
    dependency_edge_version_refs: tuple[tuple[str, str], ...] = ()
    executor_ref_snapshot: tuple[str, ...] = ()


class HandoffPublisherPort(Protocol):
    """Output port for task_handoff_ready messages, routed per executor agent."""

    def publish(self, message: HandoffReadyMessage) -> None:
        """Publish the handoff. Raises PublisherUnavailableError on transient failure."""


@dataclass(frozen=True)
class NotificationIntent:
    """A human_notification_intent or task_terminal_summary destined for email-service."""

    notification_kind: str
    recipients: tuple[str, ...]
    subject: str
    body: str
    related: dict = field(default_factory=dict)


class NotificationPublisherPort(Protocol):
    """Output port for human notifications (via email-service send_notification)."""

    def publish(self, intent: NotificationIntent) -> None:
        """Submit the notification intent. Raises PublisherUnavailableError on transient failure."""


class AgentState(StrEnum):
    """What the Registry knows about one executor ref (ai4-te1v, ai4-xkbd).

    The four values exist because the coordinator owes the task owner a
    different next step in each case: bind a workflow (nothing is listed),
    fix a bad agent id (listed but never registered), restore a retired or
    offline instance, or admit it could not ask at all.
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNREGISTERED = "unregistered"
    UNKNOWN = "unknown"


class AgentAvailabilityPort(Protocol):
    """Read-only view of executor availability from Registry registration facts."""

    def state_of(self, agent_id: str) -> AgentState:
        """Report what the Registry knows about this executor ref.

        Registry facts never authorize execution; the formal mapping
        executor_refs remains the source of execution eligibility. UNKNOWN
        (the Registry could not be consulted) must never be reported as
        UNREGISTERED -- that would turn an outage into a claim about the
        agent's existence.
        """


class PrincipalState(StrEnum):
    """Whether a notification recipient is a usable principal.

    ABSENT and UNKNOWN are deliberately distinct. ABSENT is a fact -- the
    principal does not exist or is not active -- and suppresses the send.
    UNKNOWN means the directory could not be consulted, which must not be read
    as proof of absence: the coordinator fails open and still sends.
    """

    ACTIVE = "active"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class PrincipalDirectoryPort(Protocol):
    """Read-only view of principal existence for pre-send validation."""

    def state_of(self, principal_id: str) -> PrincipalState:
        """Report whether principal_id is a valid notification recipient.

        Implementations return UNKNOWN, never ABSENT, when the directory is
        unreachable. Validation exists to reduce misdelivery, not to gate
        delivery on the availability of a separate service.
        """


class UnverifiablePrincipalDirectory:
    """Default directory used when no Registry adapter has been wired yet.

    Always UNKNOWN so that pre-send validation is a no-op and behaviour is
    unchanged until a real adapter arrives.
    """

    def state_of(self, principal_id: str) -> PrincipalState:
        return PrincipalState.UNKNOWN
