from __future__ import annotations

from dataclasses import dataclass, field
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
    edge_id: str
    source_node_id: str
    source_version_id: str
    target_node_id: str
    target_version_id: str


@dataclass(frozen=True)
class FormalSnapshot:
    """A version-consistent minimal dependency graph from get_formal_mapping_at_revision."""

    mapping_domain_id: str
    formal_revision_id: str
    nodes: tuple[TaskNodeDoc, ...] = ()
    edges: tuple[DependencyEdgeDoc, ...] = ()
    # Who last approved/published this formal revision. Answers "who made the
    # latest publish decision", not "who is appointed owner"; recipients for
    # task_terminal_summary come from here per ADR-0004. Populated from the
    # mapping MCP's published_by field (ai4-2raq); None when unavailable.
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


class AgentAvailabilityPort(Protocol):
    """Read-only view of executor availability from Registry registration facts."""

    def is_available(self, agent_id: str) -> bool:
        """True when the executor agent is registered and can receive tasks.

        Registry facts never authorize execution; the formal mapping executor_refs
        remains the source of execution eligibility. Return False when the agent
        is unregistered, retired or offline so the coordinator keeps the waiting
        fact and notifies a human instead of modifying the formal map.
        """