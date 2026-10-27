from __future__ import annotations

from dataclasses import dataclass

from .ports import (
    AgentAvailabilityPort,
    AgentState,
    FormalSnapshotPort,
    FormalSnapshot,
    HandoffPublisherPort,
    HandoffReadyMessage,
    NoSuchRevisionError,
    NotificationIntent,
    NotificationPublisherPort,
    NotificationTransportUnavailable,
    PrincipalDirectoryPort,
    PrincipalState,
    SnapshotInconsistentError,
    SnapshotUnavailableError,
    TaskNodeDoc,
    UnverifiablePrincipalDirectory,
)
from .store import (
    DISPATCH_DEAD,
    DISPATCH_FAILED,
    DISPATCH_PUBLISHED,
    DISPATCH_RESULT_UNKNOWN,
    MSG_HANDOFF_READY,
    MSG_HUMAN_NOTIFICATION,
    MSG_TERMINAL_SUMMARY,
    PENDING_DISPATCHED_UNKNOWN,
    PENDING_DONE,
    PENDING_FAILED,
    PENDING_READY,
    PENDING_SUPERSEDED,
    PENDING_WAITING,
    CoordinatorStore,
    HandoffDispatch,
    InvalidPendingTransition,
    PendingHandoff,
)


class PublisherUnavailableError(Exception):
    """Transient failure publishing a message; the dispatch may be retried."""


@dataclass(frozen=True)
class EdgeGate:
    """Result of evaluating a node's incoming dependency edges (ai4-quvy)."""

    satisfied: bool
    reason: str | None


# ai4-te1v / ai4-xkbd: the three "no usable executor" cases carry different
# next steps for the task owner, so they are three kinds rather than one.
NOTIFY_WORKFLOW_BINDING_REQUIRED = "workflow_binding_required"
NOTIFY_WORKFLOW_LOAD_FAILED = "workflow_load_failed"
NOTIFY_AGENT_UNAVAILABLE = "agent_unavailable"
# ai4-lu7y: a dependency condition the coordinator cannot evaluate is a
# fourth reason to ask a human, and it is not about the executor at all --
# reusing agent_unavailable pointed the owner at the wrong thing.
NOTIFY_DEPENDENCY_CONDITION_HOLD = "dependency_condition_hold"
NOTIFY_TERMINAL_SUMMARY = "task_terminal_summary"

#: Kinds that travel as ``human_notification_intent``; they discriminate the
#: dispatch dedupe key, so this set is what makes the key recoverable.
HUMAN_NOTIFICATION_KINDS = frozenset(
    {
        NOTIFY_WORKFLOW_BINDING_REQUIRED,
        NOTIFY_WORKFLOW_LOAD_FAILED,
        NOTIFY_AGENT_UNAVAILABLE,
        NOTIFY_DEPENDENCY_CONDITION_HOLD,
    }
)


class CoordinatorService:
    """Handoff coordinator core.

    It recomputes dependency conditions from formal mapping snapshots, keeps
    PendingHandoff/HandoffDispatch facts in its own SQLite store, publishes
    task_handoff_ready, and recovers on startup. It never opens domain stores.
    """

    def __init__(
        self,
        store: CoordinatorStore,
        snapshot_port: FormalSnapshotPort,
        publisher: HandoffPublisherPort,
        notifications: NotificationPublisherPort,
        agents: AgentAvailabilityPort,
        principals: PrincipalDirectoryPort | None = None,
        *,
        max_attempts: int = 5,
    ) -> None:
        self.store = store
        self.snapshot_port = snapshot_port
        self.publisher = publisher
        self.notifications = notifications
        self.agents = agents
        self.max_attempts = max_attempts
        # Defaults to "cannot verify", not "not found": until a Registry
        # adapter is wired, an absent one must not look like proof that a
        # principal no longer exists. `is not None` rather than `or`, because
        # a mapping-backed directory is falsy while empty and "nobody
        # registered yet" is a normal state.
        self.principals = (
            principals if principals is not None else UnverifiablePrincipalDirectory()
        )

    def on_formal_revision_published(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        """Recompute every non-root node in the published revision.

        Idempotent per trigger revision; root nodes (zero inbound edges) are
        never auto-dispatched here (ai4-te1v) - only ``dispatch_root_task``
        publishes them.
        """
        try:
            snapshot = self.snapshot_port.get_formal_mapping_at_revision(
                mapping_domain_id, formal_revision_id
            )
        except (SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError) as exc:
            self._handle_unreadable_snapshot(mapping_domain_id, formal_revision_id, exc)
            return
        self.store.clear_snapshot_failure(mapping_domain_id, formal_revision_id)
        self.store.set_latest_revision(mapping_domain_id, formal_revision_id)
        self._evaluate_snapshot(snapshot, trigger_revision_id=formal_revision_id)

    def on_task_completed(self, mapping_domain_id: str, task_node_id: str, version_ref: str) -> None:
        """Record the upstream completion fact, then recompute downstream handoffs."""
        self.store.record_completed(mapping_domain_id, task_node_id, version_ref)
        latest_revision = self.store.get_latest_revision(mapping_domain_id)
        if latest_revision is None:
            return
        snapshot = self.snapshot_port.get_formal_mapping_at_revision(mapping_domain_id, latest_revision)
        self._recompute_downstream(snapshot, completed_node_id=task_node_id)

    def startup_scan(self) -> None:
        """Recover unfinished coordination facts: re-evaluate each domain's latest
        revision and retry non-terminal dispatches. Idempotent via dedupe keys."""
        for mapping_domain_id in self.store.list_domains():
            latest = self.store.get_latest_revision(mapping_domain_id)
            if latest is None:
                continue
            try:
                snapshot = self.snapshot_port.get_formal_mapping_at_revision(mapping_domain_id, latest)
            except (SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError) as exc:
                # Same rule as the event path: keep the facts, leave a trace.
                self._handle_unreadable_snapshot(mapping_domain_id, latest, exc)
                continue
            self.store.clear_snapshot_failure(mapping_domain_id, latest)
            self._evaluate_snapshot(snapshot, trigger_revision_id=latest)
        self.retry_pending_dispatches()

    def retry_pending_dispatches(self) -> int:
        """Retry every dispatch whose outcome is not final; return how many were tried.

        Public because the runtime polls this on an interval: a non-terminal
        dispatch is a promise the coordinator has not kept yet, and leaving the
        loop to reach into a private method makes the retry policy invisible.
        """
        retried = 0
        for dispatch in self.store.list_dispatches(
            statuses=(DISPATCH_RESULT_UNKNOWN, DISPATCH_FAILED)
        ):
            self._retry_dispatch(dispatch.dispatch_id)
            retried += 1
        return retried

    def _handle_unreadable_snapshot(
        self, mapping_domain_id: str, formal_revision_id: str, exc: Exception
    ) -> None:
        """The single rule for "the snapshot could not be read" (ai4-98ye).

        Both entry points call this instead of writing their own ``except``:
        unavailable, inconsistent and no-such-revision are retryable, so the
        existing facts stay untouched and the failure becomes observable
        rather than a silent skip. A definite dispatch failure is a different
        state -- ``failed`` means the code has done everything it can.
        """
        self.store.record_snapshot_failure(
            mapping_domain_id, formal_revision_id, f"{type(exc).__name__}: {exc}"
        )

    # ------------------------------------------------------------------ core

    def _edge_gate(
        self,
        snapshot: FormalSnapshot,
        incoming: tuple[DependencyEdgeDoc, ...],
        node_ids: set[str],
    ) -> EdgeGate:
        """Evaluate every incoming edge against the ai4-te1v dependency-kind rules.

        ``satisfied`` is True only when *every* incoming edge passes. The
        per-kind rules (docs/data-flow/message-queue.md, ai4-quvy):

        - ``information``: notifies downstream; whether execution follows is the
          task's own decision -- the coordinator only requires the upstream
          completion fact.
        - ``blocking``: requires the upstream completion fact (``required_outputs``
          are treated as satisfied by that completion; the coordinator holds no
          output ledger to verify them item by item).
        - ``conditional`` / ``alternative``: an activation condition the
          coordinator cannot evaluate must NOT auto-advance the node; it parks
          the handoff waiting with ``activation_condition_unknown`` and asks a
          human (ai4-te1v). An absent condition on these kinds falls back to the
          upstream-completion rule so existing blockings keep working.
        """
        if not incoming:
            return EdgeGate(satisfied=True, reason=None)
        first_unsatisfied: DependencyEdgeDoc | None = None
        reason: str | None = None
        for edge in incoming:
            upstream_ok = (
                edge.source_node_id in node_ids
                and self.store.has_completed(
                    snapshot.mapping_domain_id,
                    edge.source_node_id,
                    self._upstream_version(snapshot, edge.source_node_id),
                )
            )
            kind = (edge.dependency_kind or "information").lower()
            if kind in {"conditional", "alternative"} and edge.activation_condition:
                # ai4-te1v: an activation condition we cannot evaluate must
                # not be guessed at; the human decides.
                first_unsatisfied = edge
                reason = "activation_condition_unknown"
                break
            if not upstream_ok:
                first_unsatisfied = edge
                reason = "blocking_dependency_missing"
                break
        return EdgeGate(satisfied=first_unsatisfied is None, reason=reason)

    def _notify_condition_hold(
        self,
        snapshot: FormalSnapshot,
        node: TaskNodeDoc,
        gate: EdgeGate,
        trigger: str,
    ) -> None:
        """Ask a human when a dependency condition cannot be auto-evaluated.

        Only for the ``activation_condition_unknown`` hold: per ai4-te1v it is
        the case where the coordinator must not guess, so the PendingHandoff
        stays waiting and a human_notification_intent is produced. A plain
        missing upstream completion is a normal waiting state, not a question
        to a human.
        """
        if gate.reason != "activation_condition_unknown":
            return
        pending = self.store.get_pending_handoff(
            snapshot.mapping_domain_id, node.task_node_id, node.version_id
        )
        if pending is None:
            return
        self._publish_human_notification(
            snapshot,
            pending,
            trigger,
            NOTIFY_DEPENDENCY_CONDITION_HOLD,
            node.executor_refs,
        )

    def _evaluate_snapshot(self, snapshot: FormalSnapshot, trigger_revision_id: str) -> None:
        node_ids = {node.task_node_id for node in snapshot.nodes}
        for node in snapshot.nodes:
            incoming = snapshot.incoming_edges(node.task_node_id)
            # ai4-te1v: root nodes (zero inbound edges) are never auto
            # dispatched on a formal-revision event. all([]) is NOT a truthy
            # condition here; only PO's dispatch_root_task may publish them.
            # ai4-hgq6: record the waiting fact anyway, so "waiting for the
            # PO" is observable instead of looking like a node that was never
            # considered.
            if not incoming:
                self._record_root_waiting(snapshot, node, trigger_revision_id)
                continue
            upstream_refs = tuple(
                (edge.source_node_id, edge.source_version_id) for edge in incoming
            )
            upstream_ids = {ref[0] for ref in upstream_refs}
            executor_refs = node.executor_refs
            executor_agent_id, notify_kind = self._select_executor(executor_refs)
            edge_gate = self._edge_gate(snapshot, incoming, node_ids)
            # ai4-quvy: a node is structurally ready when every upstream exists
            # in this snapshot and every incoming edge's gate passes -- the
            # dependency_kind rules decide what "passes" means, not a blanket
            # "all upstream complete" (ai4-te1v).
            conditions_met = edge_gate.satisfied
            if not conditions_met:
                self._upsert_pending(
                    snapshot, node, PENDING_WAITING, upstream_refs, trigger_revision_id,
                    waiting_reason=edge_gate.reason,
                )
                self._notify_condition_hold(
                    snapshot, node, edge_gate, trigger_revision_id
                )
                continue
            if not self._upsert_pending(
                snapshot, node, PENDING_READY, upstream_refs, trigger_revision_id
            ):
                # A rejected transition means the stored fact is newer than
                # this round's view; publishing anyway would duplicate work.
                continue
            dispatched = self._dispatch_ready(
                snapshot, node.task_node_id, executor_agent_id, notify_kind, trigger_revision_id
            )
            if dispatched and not snapshot.outgoing_edges(node.task_node_id):
                self._dispatch_terminal_summary(
                    snapshot, node.task_node_id, trigger_revision_id
                )

    def _record_root_waiting(
        self, snapshot: FormalSnapshot, node: TaskNodeDoc, trigger_revision_id: str
    ) -> None:
        """Leave a waiting fact for a root node without dispatching it.

        Terminal states are left untouched: a root that was dispatched and
        completed must not reappear as waiting on the next formal revision.
        """
        existing = self.store.get_pending_handoff(
            snapshot.mapping_domain_id, node.task_node_id, node.version_id
        )
        if existing is not None and existing.status in (
            PENDING_DONE,
            PENDING_SUPERSEDED,
            PENDING_FAILED,
        ):
            return
        self._upsert_pending(snapshot, node, PENDING_WAITING, (), trigger_revision_id)

    def _upsert_pending(
        self,
        snapshot: FormalSnapshot,
        node: TaskNodeDoc,
        status: str,
        upstream_refs: tuple[tuple[str, str], ...],
        trigger_revision_id: str,
        waiting_reason: str | None = None,
    ) -> bool:
        """Record the node's pending fact, tolerating a rejected transition.

        ai4-7cmr: an illegal transition keeps the stored status and lets the
        rest of the round advance. One stale node version must not stop every
        other node from being dispatched. ``waiting_reason`` is the te1v
        waiting reason (activation_condition_unknown, ...) when known.
        """
        try:
            self.store.upsert_pending_handoff(
                snapshot.mapping_domain_id,
                node.task_node_id,
                node.version_id,
                upstream_refs,
                node.executor_refs,
                status,
                trigger_revision_id,
                waiting_reason=waiting_reason,
            )
        except InvalidPendingTransition:
            return False
        return True

    def _recompute_downstream(self, snapshot: FormalSnapshot, completed_node_id: str) -> None:
        """Re-evaluate nodes that depend on the just-completed node."""
        for node in snapshot.nodes:
            incoming = snapshot.incoming_edges(node.task_node_id)
            if not any(edge.source_node_id == completed_node_id for edge in incoming):
                continue
            upstream_refs = tuple(
                (edge.source_node_id, edge.source_version_id) for edge in incoming
            )
            node_ids = {n.task_node_id for n in snapshot.nodes}
            edge_gate = self._edge_gate(snapshot, incoming, node_ids)
            executor_refs = node.executor_refs
            executor_agent_id, notify_kind = self._select_executor(executor_refs)
            if not edge_gate.satisfied:
                self._upsert_pending(
                    snapshot, node, PENDING_WAITING, upstream_refs,
                    snapshot.formal_revision_id, waiting_reason=edge_gate.reason,
                )
                self._notify_condition_hold(snapshot, node, edge_gate, f"{completed_node_id}:{snapshot.formal_revision_id}")
                continue
            if not self._upsert_pending(
                snapshot, node, PENDING_READY, upstream_refs, snapshot.formal_revision_id
            ):
                # The stored status won (e.g. a superseded version), so this
                # round has nothing new to publish for the node.
                continue
            trigger = f"{completed_node_id}:{snapshot.formal_revision_id}"
            dispatched = self._dispatch_ready(
                snapshot, node.task_node_id, executor_agent_id, notify_kind, trigger
            )
            if dispatched and not snapshot.outgoing_edges(node.task_node_id):
                self._dispatch_terminal_summary(snapshot, node.task_node_id, trigger)

    @staticmethod
    def _upstream_version(snapshot: FormalSnapshot, upstream_id: str) -> str:
        node = snapshot.node_by_id(upstream_id)
        return node.version_id if node is not None else ""

    def _incoming_edge_refs(self, snapshot: FormalSnapshot, task_node_id: str) -> tuple[tuple[str, str], ...]:
        """All incoming edge version refs for a node, as (logical_id, version_id).

        ai4-fu4i: dependency_edge_version_refs answers "which edges of the
        current formal snapshot this handoff is built on"; the pair is the
        edge's own identity, not the source node's. Stays a sequence even at
        one element so consumers never branch on cardinality (ai4-te1v).
        """
        return tuple(
            (edge.logical_id, edge.version_id)
            for edge in snapshot.incoming_edges(task_node_id)
            if edge.logical_id and edge.version_id
        )

    # ---------------------------------------------------------------- dispatch

    def _select_executor(self, executor_refs: tuple[str, ...]) -> tuple[str | None, str | None]:
        """Pick the first available executor in declared order (ai4-te1v).

        Returns ``(agent_id, notification_kind)`` with exactly one of the two
        set. ``executor_refs`` may list a collaboration set; the first
        currently available agent wins, never blindly ``refs[0]``.
        """
        if not executor_refs:
            return None, NOTIFY_WORKFLOW_BINDING_REQUIRED
        states = [(ref, self.agents.state_of(ref)) for ref in executor_refs]
        for agent_id, state in states:
            if state is AgentState.AVAILABLE:
                return agent_id, None
        # Nothing usable. Which kind depends on what the Registry knows: a ref
        # that was never registered is a mapping typo the owner must fix, a
        # registered-but-retired or offline agent is an ops problem. Answering
        # "unavailable" for both would send the owner to fix the wrong thing.
        if all(state is AgentState.UNREGISTERED for _, state in states):
            return None, NOTIFY_WORKFLOW_LOAD_FAILED
        return None, NOTIFY_AGENT_UNAVAILABLE

    def dispatch_root_task(
        self,
        mapping_domain_id: str,
        task_node_id: str,
        target_node_version_ref: str,
        *,
        trigger_revision_id: str,
    ) -> bool:
        """Explicitly dispatch a root task (ai4-te1v dispatch_root_task).

        Root nodes are never auto-dispatched on formal-revision events; the PO
        calls this idempotent entry. The node must exist in the latest
        snapshot and be a root (zero inbound edges); the executor must be
        available, otherwise the wait is kept and a human notification is
        emitted. Idempotent via the dedupe key.
        """
        latest = self.store.get_latest_revision(mapping_domain_id)
        if latest is None:
            return False
        try:
            snapshot = self.snapshot_port.get_formal_mapping_at_revision(mapping_domain_id, latest)
        except (SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError):
            return False
        node = snapshot.node_by_id(task_node_id)
        if node is None:
            return False
        if snapshot.incoming_edges(task_node_id):
            raise ValueError(
                f"task {task_node_id} is not a root node; root dispatch is for zero-inbound nodes only"
            )
        executor_agent_id, notify_kind = self._select_executor(node.executor_refs)
        self.store.upsert_pending_handoff(
            mapping_domain_id,
            task_node_id,
            target_node_version_ref,
            (),
            node.executor_refs,
            PENDING_READY,
            trigger_revision_id,
        )
        dispatched = self._dispatch_ready(
            snapshot, task_node_id, executor_agent_id, notify_kind, trigger_revision_id
        )
        if dispatched and not snapshot.outgoing_edges(task_node_id):
            self._dispatch_terminal_summary(snapshot, task_node_id, trigger_revision_id)
        return dispatched

    def _dispatch_ready(
        self,
        snapshot: FormalSnapshot,
        task_node_id: str,
        executor_agent_id: str | None,
        notify_kind: str | None,
        trigger: str,
    ) -> bool:
        """Dispatch task_handoff_ready when conditions are met and the executor
        is available. Returns True only when the handoff was actually handed
        off to the executor; human-path and unknown-result rounds return False."""
        pending = self.store.get_pending_handoff(
            snapshot.mapping_domain_id, task_node_id, snapshot.node_by_id(task_node_id).version_id
        )
        if pending is None:
            return False
        if executor_agent_id is None:
            # `_select_executor` already decided which of the three kinds the
            # owner needs to hear about; guessing one here would send them to
            # fix the wrong thing.
            self._dispatch_human_notification(
                snapshot, pending, trigger, notify_kind or NOTIFY_AGENT_UNAVAILABLE
            )
            # The waiting fact is retained: the handoff is not marked ready or
            # done until an executor becomes available.
            self.store.set_pending_handoff_status(
                snapshot.mapping_domain_id,
                pending.task_node_id,
                pending.target_node_version_ref,
                PENDING_WAITING,
            )
            return False
        dedupe_key = self._dedupe(snapshot.mapping_domain_id, pending, MSG_HANDOFF_READY, trigger)
        dispatch = self.store.create_dispatch(
            pending.pending_handoff_id, dedupe_key, MSG_HANDOFF_READY, executor_agent_id
        )
        if dispatch is None or dispatch.status in (DISPATCH_PUBLISHED,):
            return dispatch is not None and dispatch.status in (DISPATCH_PUBLISHED,)
        try:
            self.publisher.publish(
                HandoffReadyMessage(
                    mapping_domain_id=snapshot.mapping_domain_id,
                    task_node_id=pending.task_node_id,
                    target_node_version_ref=pending.target_node_version_ref,
                    target_agent_id=executor_agent_id,
                    pending_handoff_id=pending.pending_handoff_id,
                    trigger_revision_id=trigger,
                    upstream_source_refs=pending.upstream_source_refs,
                    # ai4-fu4i: every incoming edge's (logical_id, version_id),
                    # so the downstream agent can see exactly which edges of the
                    # formal snapshot this handoff is built on.
                    dependency_edge_version_refs=self._incoming_edge_refs(
                        snapshot, pending.task_node_id
                    ),
                    # ai4-7uxz: the full list, so a later review can tell
                    # "nobody else was configured" from "someone was, and the
                    # wrong one was picked". Audit only, never authorization.
                    executor_ref_snapshot=pending.executor_refs,
                )
            )
        except Exception as exc:  # transient publish failures are retried
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=1
            )
            self.store.set_pending_handoff_status(
                snapshot.mapping_domain_id,
                pending.task_node_id,
                pending.target_node_version_ref,
                PENDING_DISPATCHED_UNKNOWN,
            )
            return False
        self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=1)
        self.store.set_pending_handoff_status(
            snapshot.mapping_domain_id,
            pending.task_node_id,
            pending.target_node_version_ref,
            PENDING_DONE,
        )
        return True

    def _dispatch_human_notification(
        self,
        snapshot: FormalSnapshot,
        pending: PendingHandoff,
        trigger: str,
        notification_kind: str,
    ) -> None:
        node = snapshot.node_by_id(pending.task_node_id)
        self._publish_human_notification(
            snapshot,
            pending,
            trigger,
            notification_kind,
            node.executor_refs if node is not None else (),
        )

    def _publish_human_notification(
        self,
        snapshot: FormalSnapshot,
        pending: PendingHandoff,
        trigger: str,
        notification_kind: str,
        executor_refs: tuple[str, ...],
    ) -> bool:
        """Send one human notification for one reason.

        Returns True when it was published (or already had been). Callers own
        the PendingHandoff status: this only decides whether a notification
        may be addressed at all, so the same gate applies to every kind.
        """
        node = snapshot.node_by_id(pending.task_node_id)
        recipient = node.task_owner_id if node is not None else None
        # ai4-f985: one notification has exactly one recipient, the task
        # owner's principal_id. A missing owner means corrupt data: do not
        # guess a recipient, and surface the gap.
        if not recipient:
            self._record_unresolved_recipient(
                snapshot,
                pending,
                trigger,
                "recipient_unresolved:task_owner_id_missing",
                notification_kind=notification_kind,
            )
            return False
        # ai4-xkbd: validate the recipient before sending. ABSENT is a fact
        # (the principal does not exist or is inactive) and suppresses the
        # send; UNKNOWN means the directory could not be consulted, and
        # failing closed there would stop every notification whenever the
        # Registry is down -- a worse outcome than an occasional misdelivery.
        if self.principals.state_of(recipient) is PrincipalState.ABSENT:
            self._record_unresolved_recipient(
                snapshot,
                pending,
                trigger,
                "recipient_unresolved:principal_absent",
                notification_kind=notification_kind,
            )
            return False
        # ai4-lu7y: the kind is part of the key. Without it, a node version
        # that first parked on a dependency condition could never tell its
        # owner that the executor had also gone away -- the second
        # notification collided with the first and was skipped as published.
        dedupe_key = self._dedupe(
            snapshot.mapping_domain_id,
            pending,
            MSG_HUMAN_NOTIFICATION,
            trigger,
            discriminator=notification_kind,
        )
        dispatch = self.store.create_dispatch(
            pending.pending_handoff_id, dedupe_key, MSG_HUMAN_NOTIFICATION, None
        )
        if dispatch is None:
            return False
        if dispatch.status in (DISPATCH_PUBLISHED,):
            return True
        subject, body = self._human_notification_content(
            notification_kind, pending.task_node_id, executor_refs
        )
        try:
            self.notifications.publish(
                NotificationIntent(
                    notification_kind=notification_kind,
                    recipients=(recipient,),
                    subject=subject,
                    body=body,
                    related={
                        "mapping_domain_id": snapshot.mapping_domain_id,
                        "task_node_id": pending.task_node_id,
                        "pending_handoff_id": pending.pending_handoff_id,
                    },
                )
            )
        except NotificationTransportUnavailable as exc:
            # Not a delivery failure: nothing was attempted because the email
            # endpoint is not configured. Keep the dispatch retryable instead
            # of calling it published, or the owner would never be told.
            self.store.set_dispatch_status(
                dispatch.dispatch_id,
                DISPATCH_FAILED,
                f"notification_transport_unconfigured: {exc}",
                attempt_count=1,
            )
            return False
        except Exception as exc:
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=1
            )
            return False
        self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=1)
        return True

    def _record_unresolved_recipient(
        self,
        snapshot: FormalSnapshot,
        pending: PendingHandoff,
        trigger: str,
        reason: str,
        message_type: str = MSG_HUMAN_NOTIFICATION,
        notification_kind: str | None = None,
    ) -> None:
        """Keep an observable record when no notification could be addressed.

        The dispatch row is what an operator can query; without it a corrupt
        TaskNode would look identical to a task nobody needed to notify.
        """
        failed_dispatch = self.store.create_dispatch(
            pending.pending_handoff_id,
            self._dedupe(
                snapshot.mapping_domain_id,
                pending,
                message_type,
                trigger,
                discriminator=notification_kind,
            ),
            message_type,
            None,
        )
        if failed_dispatch is not None:
            self.store.set_dispatch_status(
                failed_dispatch.dispatch_id, DISPATCH_FAILED, reason
            )

    @staticmethod
    def _human_notification_content(
        notification_kind: str, task_node_id: str, executor_refs: tuple[str, ...]
    ) -> tuple[str, str]:
        """Subject and body for each reason a human has to step in.

        The kinds exist because the owner's next action differs: judge a
        condition, bind a workflow, correct an agent id, or restore an
        instance. A shared body would leave the owner guessing which applies.
        """
        if notification_kind == NOTIFY_DEPENDENCY_CONDITION_HOLD:
            return (
                "任务交接等待激活条件判定",
                f"TaskNode {task_node_id} 的入边带激活条件，交接协调无法自动判定，"
                "因此没有放行。请判断条件是否满足后手动推进。",
            )
        if notification_kind == NOTIFY_WORKFLOW_BINDING_REQUIRED:
            return (
                "任务交接缺少执行者绑定",
                f"TaskNode {task_node_id} 的 executor_refs 为空，没有可派发的执行者。"
                "请为该节点登记 Workflow 并补上 executor_refs，或自行接手执行。",
            )
        if notification_kind == NOTIFY_WORKFLOW_LOAD_FAILED:
            listed = "、".join(executor_refs) or "（空）"
            return (
                "任务交接指向未登记的执行者",
                f"TaskNode {task_node_id} 的 executor_refs（{listed}）指向未登记的 agent_id。"
                "请核对 agent_id 是否拼写错误，或先在 Registry 登记该 Workflow。",
            )
        return (
            "任务交接等待人工处理",
            f"TaskNode {task_node_id} 的执行者已注销或无可用运行实例。"
            "请恢复运行实例，或自行接手执行。",
        )

    def _dispatch_terminal_summary(
        self, snapshot: FormalSnapshot, task_node_id: str, trigger: str
    ) -> None:
        pending = self.store.get_pending_handoff(
            snapshot.mapping_domain_id, task_node_id, snapshot.node_by_id(task_node_id).version_id
        )
        if pending is None:
            return
        # ADR-0004 / ai4-10ja#6: the terminal summary goes to whoever last
        # published the formal revision, not the mapping domain id.
        recipient = snapshot.latest_published_by
        if not recipient:
            # ai4-xkbd: same rule as a missing task owner - say so instead of
            # leaving the chain's end unrecorded.
            self._record_unresolved_recipient(
                snapshot,
                pending,
                trigger,
                "recipient_unresolved:latest_published_by_missing",
                MSG_TERMINAL_SUMMARY,
            )
            return
        if self.principals.state_of(recipient) is PrincipalState.ABSENT:
            self._record_unresolved_recipient(
                snapshot,
                pending,
                trigger,
                "recipient_unresolved:principal_absent",
                MSG_TERMINAL_SUMMARY,
            )
            return
        dedupe_key = self._dedupe(
            snapshot.mapping_domain_id, pending, MSG_TERMINAL_SUMMARY, trigger
        )
        dispatch = self.store.create_dispatch(
            pending.pending_handoff_id, dedupe_key, MSG_TERMINAL_SUMMARY, None
        )
        if dispatch is None or dispatch.status in (DISPATCH_PUBLISHED,):
            return
        try:
            self.notifications.publish(
                NotificationIntent(
                    notification_kind=NOTIFY_TERMINAL_SUMMARY,
                    recipients=(recipient,),
                    subject="任务链已到终点",
                    body=f"TaskNode {task_node_id} 无后继节点，工作流已结束。",
                    related={
                        "mapping_domain_id": snapshot.mapping_domain_id,
                        "task_node_id": task_node_id,
                        "formal_revision_id": snapshot.formal_revision_id,
                    },
                )
            )
        except Exception as exc:
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=1
            )
            return
        self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=1)

    def _retry_dispatch(self, dispatch_id: str) -> None:
        dispatch = self.store.get_dispatch(dispatch_id)
        if dispatch is None:
            return
        pending = self.store.get_pending_handoff_by_id(dispatch.pending_handoff_id)
        if pending is None:
            return
        # ai4-te1v: this retry is one more attempt. Reaching max_attempts with
        # the outcome still unconfirmed moves the dispatch to dead.
        attempt_count = dispatch.attempt_count + 1
        if attempt_count >= self.max_attempts:
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_DEAD, "max_attempts_exceeded", attempt_count=attempt_count
            )
            return
        latest_revision_id = self.store.get_latest_revision(pending.mapping_domain_id)
        if latest_revision_id is None:
            self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_FAILED, "no_revision")
            return
        try:
            snapshot = self.snapshot_port.get_formal_mapping_at_revision(
                pending.mapping_domain_id, latest_revision_id
            )
            if snapshot.node_by_id(pending.task_node_id) is None:
                self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_FAILED, "node_missing")
                return
        except (SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError) as exc:
            # ai4-te1v: unavailable/inconsistent are retryable - keep the
            # fact and wait; only a definite unrecoverable state becomes failed.
            # The trace is the same one the startup scan leaves, so the two
            # entry points cannot disagree about what happened (ai4-98ye).
            self._handle_unreadable_snapshot(pending.mapping_domain_id, latest_revision_id, exc)
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, str(exc), attempt_count=attempt_count
            )
            return
        self._publish_dispatch(dispatch, snapshot, attempt_count=attempt_count)

    def _publish_dispatch(self, dispatch: HandoffDispatch, snapshot: FormalSnapshot, attempt_count: int = 1) -> None:
        """Re-publish an existing dispatch record (startup recovery). Uses the
        record's own dedupe_key as trigger so re-publishing stays idempotent."""
        pending = self.store.get_pending_handoff_by_id(dispatch.pending_handoff_id)
        if pending is None:
            self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_FAILED, "pending_missing")
            return
        if dispatch.message_type == MSG_HANDOFF_READY:
            try:
                self.publisher.publish(
                    HandoffReadyMessage(
                        mapping_domain_id=snapshot.mapping_domain_id,
                        task_node_id=pending.task_node_id,
                        target_node_version_ref=pending.target_node_version_ref,
                        target_agent_id=dispatch.target_agent_id or "",
                        pending_handoff_id=pending.pending_handoff_id,
                        trigger_revision_id=dispatch.dedupe_key,
                        upstream_source_refs=pending.upstream_source_refs,
                        # ai4-fu4i: same edge refs as the first dispatch; kept
                        # consistent across retries so the recovery message
                        # carries the same snapshot identity.
                        dependency_edge_version_refs=self._incoming_edge_refs(
                            snapshot, pending.task_node_id
                        ),
                        executor_ref_snapshot=pending.executor_refs,
                    )
                )
            except Exception as exc:
                self.store.set_dispatch_status(
                    dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=attempt_count
                )
                return
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=attempt_count
            )
            self.store.set_pending_handoff_status(
                pending.mapping_domain_id,
                pending.task_node_id,
                pending.target_node_version_ref,
                PENDING_DONE,
            )
            return
        if dispatch.message_type == MSG_TERMINAL_SUMMARY:
            recipient = snapshot.latest_published_by
            if not recipient:
                self.store.set_dispatch_status(
                    dispatch.dispatch_id, DISPATCH_FAILED, "recipient_unresolved:latest_published_by_missing", attempt_count=attempt_count
                )
                return
            try:
                self.notifications.publish(
                    NotificationIntent(
                        notification_kind="task_terminal_summary",
                        recipients=(recipient,),
                        subject="任务链已到终点",
                        body=f"TaskNode {pending.task_node_id} 无后继节点，工作流已结束。",
                        related={
                            "mapping_domain_id": snapshot.mapping_domain_id,
                            "task_node_id": pending.task_node_id,
                            "formal_revision_id": snapshot.formal_revision_id,
                        },
                    )
                )
            except Exception as exc:
                self.store.set_dispatch_status(
                    dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=attempt_count
                )
                return
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=attempt_count
            )
            return
        node = snapshot.node_by_id(pending.task_node_id)
        recipient = node.task_owner_id if node is not None else None
        if not recipient:
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_FAILED, "recipient_unresolved:task_owner_id_missing", attempt_count=attempt_count
            )
            return
        if self.principals.state_of(recipient) is PrincipalState.ABSENT:
            # Same gate as the first send: a recipient that has since been
            # deactivated must not be retried into an inbox that no longer
            # exists.
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_FAILED, "recipient_unresolved:principal_absent", attempt_count=attempt_count
            )
            return
        # ai4-lu7y: retry the notification this row was created for. The key
        # carries the kind, so a retry cannot silently turn a "judge this
        # condition" mail into an "executor is gone" one; rows written before
        # the key carried a kind fall back to re-deriving it from the current
        # Registry state.
        notification_kind = self._kind_from_dedupe(dispatch.dedupe_key)
        if notification_kind is None:
            _, notification_kind = self._select_executor(node.executor_refs if node else ())
        notification_kind = notification_kind or NOTIFY_AGENT_UNAVAILABLE
        subject, body = self._human_notification_content(
            notification_kind,
            pending.task_node_id,
            node.executor_refs if node else (),
        )
        try:
            self.notifications.publish(
                NotificationIntent(
                    notification_kind=notification_kind,
                    recipients=(recipient,),
                    subject=subject,
                    body=body,
                    related={
                        "mapping_domain_id": snapshot.mapping_domain_id,
                        "task_node_id": pending.task_node_id,
                        "pending_handoff_id": pending.pending_handoff_id,
                    },
                )
            )
        except NotificationTransportUnavailable as exc:
            self.store.set_dispatch_status(
                dispatch.dispatch_id,
                DISPATCH_FAILED,
                f"notification_transport_unconfigured: {exc}",
                attempt_count=attempt_count,
            )
            return
        except Exception as exc:
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=attempt_count
            )
            return
        self.store.set_dispatch_status(
            dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=attempt_count
        )

    @staticmethod
    def _kind_from_dedupe(dedupe_key: str) -> str | None:
        """Recover the notification kind a dispatch row was created for."""
        kind = dedupe_key.rpartition(":")[2]
        return kind if kind in HUMAN_NOTIFICATION_KINDS else None

    @staticmethod
    def _dedupe(
        mapping_domain_id: str,
        pending: PendingHandoff,
        message_type: str,
        trigger: str,
        discriminator: str | None = None,
    ) -> str:
        # ai4-te1v: the dispatch idempotency key must NOT carry the trigger
        # revision - "same node version, same message type" dispatches once
        # even when new formal revisions arrive.
        # ai4-lu7y: it does carry the reason, because one message type can
        # have several: two different notifications about the same node
        # version are two facts, not a repeat of one.
        key = (
            f"{mapping_domain_id}:{pending.task_node_id}:"
            f"{pending.target_node_version_ref}:{message_type}"
        )
        return f"{key}:{discriminator}" if discriminator else key