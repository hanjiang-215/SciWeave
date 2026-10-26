from __future__ import annotations

from typing import Protocol

from .ports import (
    AgentAvailabilityPort,
    FormalSnapshotPort,
    FormalSnapshot,
    HandoffPublisherPort,
    HandoffReadyMessage,
    NoSuchRevisionError,
    NotificationIntent,
    NotificationPublisherPort,
    SnapshotInconsistentError,
    SnapshotUnavailableError,
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
    PendingHandoff,
)


class PublisherUnavailableError(Exception):
    """Transient failure publishing a message; the dispatch may be retried."""


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
        *,
        max_attempts: int = 5,
    ) -> None:
        self.store = store
        self.snapshot_port = snapshot_port
        self.publisher = publisher
        self.notifications = notifications
        self.agents = agents
        self.max_attempts = max_attempts

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
        except (SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError):
            # 快照不可读：保持既有事实，等待下次事件或启动扫描重试；
            # 不可恢复错误也不在此污染状态，交由人工路径处置。
            return
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
            except (SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError):
                continue
            self._evaluate_snapshot(snapshot, trigger_revision_id=latest)
        for dispatch in self.store.list_dispatches(
            statuses=(DISPATCH_RESULT_UNKNOWN, DISPATCH_FAILED)
        ):
            self._retry_dispatch(dispatch.dispatch_id)

    # ------------------------------------------------------------------ core

    def _evaluate_snapshot(self, snapshot: FormalSnapshot, trigger_revision_id: str) -> None:
        node_ids = {node.task_node_id for node in snapshot.nodes}
        for node in snapshot.nodes:
            incoming = snapshot.incoming_edges(node.task_node_id)
            # ai4-te1v: root nodes (zero inbound edges) are never auto
            # dispatched on a formal-revision event. all([]) is NOT a truthy
            # condition here; only PO's dispatch_root_task may publish them.
            if not incoming:
                continue
            upstream_refs = tuple(
                (edge.source_node_id, edge.source_version_id) for edge in incoming
            )
            upstream_ids = {ref[0] for ref in upstream_refs}
            executor_refs = node.executor_refs
            executor_agent_id = self._select_executor(executor_refs)
            # A node is structurally ready when every upstream exists in this
            # snapshot and has a recorded completion fact.
            conditions_met = all(
                upstream_id in node_ids and self.store.has_completed(
                    snapshot.mapping_domain_id, upstream_id, self._upstream_version(snapshot, upstream_id)
                )
                for upstream_id in upstream_ids
            )
            if not conditions_met:
                self.store.upsert_pending_handoff(
                    snapshot.mapping_domain_id,
                    node.task_node_id,
                    node.version_id,
                    upstream_refs,
                    executor_refs,
                    PENDING_WAITING,
                    trigger_revision_id,
                )
                continue
            self.store.upsert_pending_handoff(
                snapshot.mapping_domain_id,
                node.task_node_id,
                node.version_id,
                upstream_refs,
                executor_refs,
                PENDING_READY,
                trigger_revision_id,
            )
            dispatched = self._dispatch_ready(
                snapshot, node.task_node_id, executor_agent_id, trigger_revision_id
            )
            if dispatched and not snapshot.outgoing_edges(node.task_node_id):
                self._dispatch_terminal_summary(
                    snapshot, node.task_node_id, trigger_revision_id
                )

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
            conditions_met = all(
                upstream_id in node_ids
                and self.store.has_completed(
                    snapshot.mapping_domain_id,
                    upstream_id,
                    self._upstream_version(snapshot, upstream_id),
                )
                for upstream_id in {ref[0] for ref in upstream_refs}
            )
            executor_refs = node.executor_refs
            executor_agent_id = self._select_executor(executor_refs)
            if not conditions_met:
                self.store.upsert_pending_handoff(
                    snapshot.mapping_domain_id,
                    node.task_node_id,
                    node.version_id,
                    upstream_refs,
                    executor_refs,
                    PENDING_WAITING,
                    snapshot.formal_revision_id,
                )
                continue
            self.store.upsert_pending_handoff(
                snapshot.mapping_domain_id,
                node.task_node_id,
                node.version_id,
                upstream_refs,
                executor_refs,
                PENDING_READY,
                snapshot.formal_revision_id,
            )
            trigger = f"{completed_node_id}:{snapshot.formal_revision_id}"
            dispatched = self._dispatch_ready(snapshot, node.task_node_id, executor_agent_id, trigger)
            if dispatched and not snapshot.outgoing_edges(node.task_node_id):
                self._dispatch_terminal_summary(snapshot, node.task_node_id, trigger)

    @staticmethod
    def _upstream_version(snapshot: FormalSnapshot, upstream_id: str) -> str:
        node = snapshot.node_by_id(upstream_id)
        return node.version_id if node is not None else ""

    # ---------------------------------------------------------------- dispatch

    def _select_executor(self, executor_refs: tuple[str, ...]) -> str | None:
        """Pick the first available executor in declared order (ai4-te1v).

        ``executor_refs`` may list a collaboration set; the first currently
        available agent wins, never blindly ``refs[0]``. Returns None when
        every ref is unavailable or the list is empty.
        """
        for agent_id in executor_refs:
            if self.agents.is_available(agent_id):
                return agent_id
        return None

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
        executor_agent_id = self._select_executor(node.executor_refs)
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
            snapshot, task_node_id, executor_agent_id, trigger_revision_id
        )
        if dispatched and not snapshot.outgoing_edges(task_node_id):
            self._dispatch_terminal_summary(snapshot, task_node_id, trigger_revision_id)
        return dispatched

    def _dispatch_ready(
        self,
        snapshot: FormalSnapshot,
        task_node_id: str,
        executor_agent_id: str | None,
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
        if executor_agent_id is None or not self.agents.is_available(executor_agent_id):
            self._dispatch_human_notification(snapshot, pending, trigger)
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
        self, snapshot: FormalSnapshot, pending: PendingHandoff, trigger: str
    ) -> None:
        node = snapshot.node_by_id(pending.task_node_id)
        recipient = node.task_owner_id if node is not None else None
        # ai4-f985: one notification has exactly one recipient, the task
        # owner's principal_id. A missing owner means corrupt data: keep the
        # waiting fact, do not guess a recipient, and surface the gap.
        if not recipient:
            self.store.set_pending_handoff_status(
                snapshot.mapping_domain_id,
                pending.task_node_id,
                pending.target_node_version_ref,
                PENDING_WAITING,
            )
            failed_dispatch = self.store.create_dispatch(
                pending.pending_handoff_id,
                self._dedupe(snapshot.mapping_domain_id, pending, MSG_HUMAN_NOTIFICATION, trigger),
                MSG_HUMAN_NOTIFICATION,
                None,
            )
            if failed_dispatch is not None:
                self.store.set_dispatch_status(
                    failed_dispatch.dispatch_id,
                    DISPATCH_FAILED,
                    "recipient_unresolved:task_owner_id_missing",
                )
            return
        dedupe_key = self._dedupe(
            snapshot.mapping_domain_id, pending, MSG_HUMAN_NOTIFICATION, trigger
        )
        dispatch = self.store.create_dispatch(
            pending.pending_handoff_id, dedupe_key, MSG_HUMAN_NOTIFICATION, None
        )
        if dispatch is None or dispatch.status in (DISPATCH_PUBLISHED,):
            return
        try:
            self.notifications.publish(
                NotificationIntent(
                    notification_kind="agent_unavailable",
                    recipients=(recipient,),
                    subject="任务交接等待人工处理",
                    body=f"TaskNode {pending.task_node_id} 的执行者不可用，交接事实已保留。",
                    related={
                        "mapping_domain_id": snapshot.mapping_domain_id,
                        "task_node_id": pending.task_node_id,
                        "pending_handoff_id": pending.pending_handoff_id,
                    },
                )
            )
        except Exception as exc:
            self.store.set_dispatch_status(
                dispatch.dispatch_id, DISPATCH_RESULT_UNKNOWN, error_summary=str(exc), attempt_count=1
            )
            return
        self.store.set_dispatch_status(dispatch.dispatch_id, DISPATCH_PUBLISHED, attempt_count=1)

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
                    notification_kind="task_terminal_summary",
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
        try:
            self.notifications.publish(
                NotificationIntent(
                    notification_kind="agent_unavailable",
                    recipients=(recipient,),
                    subject="任务交接等待人工处理",
                    body=f"TaskNode {pending.task_node_id} 的执行者不可用，交接事实已保留。",
                    related={
                        "mapping_domain_id": snapshot.mapping_domain_id,
                        "task_node_id": pending.task_node_id,
                        "pending_handoff_id": pending.pending_handoff_id,
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

    @staticmethod
    def _dedupe(
        mapping_domain_id: str, pending: PendingHandoff, message_type: str, trigger: str
    ) -> str:
        # ai4-te1v: the dispatch idempotency key must NOT carry the trigger
        # revision - "same node version, same message type" dispatches once
        # even when new formal revisions arrive.
        return f"{mapping_domain_id}:{pending.task_node_id}:{pending.target_node_version_ref}:{message_type}"