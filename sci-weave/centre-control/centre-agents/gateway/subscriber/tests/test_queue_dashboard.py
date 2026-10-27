"""Behavior tests for the queue dashboard source (ai4-nvuj).

Covers the three cases the ticket asks for: a healthy fragment, an unavailable
store, and a malformed/unauthorized HTTP exchange. No broker, model credential
or fixed port is required.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from task_agent_worker.store import ExecutionStore

from gateway_subscriber.dashboard_source import (
    build_queue_fragment,
    create_queue_dashboard_server,
)
from gateway_subscriber.queue import QueueMessage
from gateway_subscriber.service import SubscriberService


class _BrokenStore:
    """Store whose health probe and audit read both fail."""

    def health(self) -> bool:
        raise RuntimeError("storage gone")

    def list_recent_audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        raise RuntimeError("storage gone")


class _HalfBrokenStore:
    """Health looks fine but the audit read fails."""

    def health(self) -> bool:
        return True

    def list_recent_audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        raise RuntimeError("audit gone")


class QueueFragmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "queue.sqlite3"))
        self.service = SubscriberService(self.store, "centre-agent")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _deliver(self, task_node_id: str = "t1", revision: str = "rev-1") -> None:
        self.service.handle_message(
            QueueMessage(
                topic="handoff",
                partition=0,
                offset=0,
                key="event-1",
                payload={
                    "target": {"id": task_node_id},
                    "payload": {"formal_revision_id": revision},
                },
            )
        )

    def test_healthy_fragment_uses_front_end_vocabulary(self) -> None:
        self._deliver()

        fragment = build_queue_fragment(
            store=self.store, topics=["handoff"], group_id="group-1", queue_kind="kafka"
        )

        self.assertEqual(fragment["sourceStatus"], "fresh")
        self.assertTrue(fragment["observedAt"])
        services = {item["id"]: item for item in fragment["services"]}
        self.assertIn("subscriber", services)
        self.assertIn("queue", services)
        self.assertIn("consumer-group", services)
        for service in services.values():
            # web-ui `isService` validates exactly these keys and values.
            self.assertTrue(service["name"])
            self.assertEqual(service["role"], "centre-agent")
            self.assertIn(service["status"], {"online", "stale", "unavailable", "unknown"})

    def test_audit_events_are_projected_into_the_fragment(self) -> None:
        self._deliver()

        fragment = build_queue_fragment(
            store=self.store, topics=["handoff"], group_id=None, queue_kind="fake"
        )

        self.assertTrue(fragment["events"], "queue events must not be empty after a delivery")
        for event in fragment["events"]:
            self.assertTrue(event["id"])
            self.assertTrue(event["title"])
            self.assertTrue(event["occurredAt"])
            self.assertIn(
                event["type"],
                {"formal_release", "candidate_change", "message_received", "execution_completed", "mcp_failure"},
            )

    def test_broken_store_degrades_to_unavailable(self) -> None:
        fragment = build_queue_fragment(
            store=_BrokenStore(), topics=["handoff"], group_id=None, queue_kind="fake"
        )

        self.assertEqual(fragment["sourceStatus"], "unavailable")
        self.assertEqual(fragment["events"], [])
        for service in fragment["services"]:
            self.assertEqual(service["status"], "unavailable")

    def test_audit_read_failure_keeps_services_but_hides_events(self) -> None:
        fragment = build_queue_fragment(
            store=_HalfBrokenStore(), topics=["handoff"], group_id="g", queue_kind="fake"
        )

        self.assertEqual(fragment["sourceStatus"], "unavailable")
        self.assertEqual(fragment["events"], [])
        self.assertEqual(fragment["services"][0]["status"], "online")


class QueueDashboardHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "queue.sqlite3"))
        self.fragment = build_queue_fragment(
            store=self.store, topics=["handoff"], group_id=None, queue_kind="fake"
        )
        self.server = create_queue_dashboard_server(
            lambda: self.fragment, host="127.0.0.1", port=0, token="probe-token"
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.store.close()
        self.temp.cleanup()

    def _get(self, path: str, token: str | None = None) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(self.base + path, method="GET")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_health_is_open(self) -> None:
        status, payload = self._get("/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")

    def test_source_requires_token_when_configured(self) -> None:
        status, payload = self._get("/api/dashboard/source/queue")

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_source_returns_fragment_with_token(self) -> None:
        status, payload = self._get("/api/dashboard/source/queue", token="probe-token")

        self.assertEqual(status, 200)
        self.assertEqual(payload["sourceStatus"], "fresh")
        self.assertIn("services", payload)
        self.assertIn("events", payload)

    def test_gateway_style_alias_is_served(self) -> None:
        status, payload = self._get("/sources", token="probe-token")

        self.assertEqual(status, 200)
        self.assertEqual(payload["sourceStatus"], "fresh")

    def test_unknown_path_is_not_found(self) -> None:
        status, payload = self._get("/nope", token="probe-token")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")


class DashboardWiringTests(unittest.TestCase):
    """The endpoint is opt-in: no port configured means no listener."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "wiring.sqlite3"))
        self._saved = {
            name: os.environ.pop(name, None)
            for name in (
                "SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT",
                "SCIWEAVE_SUBSCRIBER_DASHBOARD_HOST",
                "SCIWEAVE_SUBSCRIBER_DASHBOARD_TOKEN",
            )
        }

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.store.close()
        self.temp.cleanup()

    def test_no_port_means_no_server(self) -> None:
        from gateway_subscriber.cli import start_dashboard_server

        self.assertIsNone(start_dashboard_server(self.store, ["handoff"], None, "fake"))

    def test_port_starts_and_stops_a_server(self) -> None:
        from gateway_subscriber.cli import start_dashboard_server

        os.environ["SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT"] = "0"
        os.environ["SCIWEAVE_SUBSCRIBER_DASHBOARD_HOST"] = "127.0.0.1"
        server = start_dashboard_server(self.store, ["handoff"], "group-1", "fake")
        self.assertIsNotNone(server)
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
                self.assertEqual(json.loads(response.read())["status"], "ready")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
