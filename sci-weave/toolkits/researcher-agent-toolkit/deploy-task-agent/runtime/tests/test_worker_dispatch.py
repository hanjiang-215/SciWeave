"""The subscriber dispatches to a short-lived worker process (ai4-0fwc).

Two things are pinned here that no test could reach before:

* `WorkerSubprocess` really starts a separate process and reads its result;
* `WorkAgentRuntime` holds the **durable** lease across that process, so a
  second delivery for the same target is refused while the first runs, and a
  second *process* cannot take the same target either.

The subprocess tests run the shipped `service-template/worker/src/main.py` as a
real process. That is deliberate: the bug was that nothing started it, so a
mock would reproduce exactly the blind spot that let it ship.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from work_agent_runtime import (
    InboxStore,
    SqliteExecutionStore,
    WorkerLease,
    WorkAgentRuntime,
)
from work_agent_runtime.worker_dispatch import (
    WorkerDispatchError,
    WorkerRun,
    WorkerSubprocess,
    _draft_id_from,
)

KIT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SRC = Path(__file__).resolve().parents[1] / "src"


class _Outcome:
    def __init__(self, status: str, draft_id: str | None = None) -> None:
        self.status = status
        self.draft_id = draft_id


class _Recorder:
    """A dispatcher that records calls instead of starting a process."""

    def __init__(self, status: str = "completed", draft_id: str | None = "draft-1") -> None:
        self.calls: list[str] = []
        self.status = status
        self.draft_id = draft_id

    def __call__(self, dedupe_key: str) -> _Outcome:
        self.calls.append(dedupe_key)
        return _Outcome(self.status, self.draft_id)


class DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = str(Path(self._tmp.name) / "kit.sqlite3")
        self.inbox = InboxStore(self.db)
        self.addCleanup(self.inbox.close)

    def _runtime(self, dispatcher) -> WorkAgentRuntime:
        runtime = WorkAgentRuntime(inbox=self.inbox, dispatcher=dispatcher)
        runtime.lease = WorkerLease(self.db)
        self.addCleanup(runtime.lease.close)
        return runtime

    def test_a_dispatched_handoff_runs_the_worker_instead_of_inline(self) -> None:
        recorder = _Recorder()
        record = self._runtime(recorder).handle_inbound("node-1", "evt-1")
        self.assertEqual(recorder.calls, ["node-1:evt-1"])
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.draft_id, "draft-1")

    def test_the_inline_draft_write_never_happens_on_the_dispatch_path(self) -> None:
        """The old `f"{agent_definition}:{event_id}"` payload must not appear.

        That string was the observable symptom of "no model was called": the
        subscriber wrote a draft itself. Once dispatch is wired, the subscriber
        writes nothing — the worker owns the draft-box credential.
        """
        runtime = self._runtime(_Recorder())
        runtime.drafts.write = lambda **kwargs: self.fail(f"subscriber wrote a draft: {kwargs}")
        self.assertEqual(runtime.handle_inbound("node-1", "evt-1").status, "completed")

    def test_a_failed_worker_leaves_the_row_queued_for_replay(self) -> None:
        runtime = self._runtime(_Recorder(status="failed"))
        record = runtime.handle_inbound("node-1", "evt-1")
        self.assertEqual(record.status, "failed")
        self.assertEqual(self.inbox.get("node-1:evt-1")["status"], "queued")

    def test_a_second_delivery_while_the_lease_is_held_runs_nothing(self) -> None:
        """The lease is acquired before the subprocess, so this is the real window."""
        recorder = _Recorder()
        runtime = self._runtime(recorder)
        self.assertTrue(runtime.lease.acquire("node-1"))
        try:
            record = runtime.handle_inbound("node-1", "evt-2")
        finally:
            runtime.lease.release("node-1")
        self.assertEqual(recorder.calls, [], "a held lease must not start a worker")
        self.assertEqual(record.status, "queued")

    def test_the_lease_is_released_after_dispatch_even_when_the_worker_fails(self) -> None:
        runtime = self._runtime(_Recorder(status="failed"))
        runtime.handle_inbound("node-1", "evt-1")
        self.assertIsNone(runtime.lease.holder("node-1"))

    def test_drain_requeues_a_row_a_crashed_dispatch_left_behind(self) -> None:
        """Commit-then-run means a crash leaves a queued row, not a lost handoff."""
        self.inbox.enqueue("node-1:evt-1", "node-1", "evt-1", binding_present=True)
        recorder = _Recorder()
        results = self._runtime(recorder).drain_queued()
        self.assertEqual(recorder.calls, ["node-1:evt-1"])
        self.assertEqual([record.status for record in results], ["completed"])


class LeaseAcrossProcessesTests(unittest.TestCase):
    """A `threading.Lock` cannot do this; a SQLite row can."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = str(Path(self._tmp.name) / "lease.sqlite3")

    def _hold_in_another_process(self, target_id: str) -> subprocess.CompletedProcess:
        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(RUNTIME_SRC)!r})
            from work_agent_runtime import WorkerLease
            lease = WorkerLease({self.db!r})
            print("acquired" if lease.acquire({target_id!r}) else "refused")
            """
        )
        return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)

    def test_another_process_cannot_take_a_held_target(self) -> None:
        lease = WorkerLease(self.db)
        self.addCleanup(lease.close)
        self.assertTrue(lease.acquire("node-1"))
        result = self._hold_in_another_process("node-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "refused")

    def test_an_unrelated_target_is_free_in_another_process(self) -> None:
        lease = WorkerLease(self.db)
        self.addCleanup(lease.close)
        self.assertTrue(lease.acquire("node-1"))
        self.assertEqual(self._hold_in_another_process("node-2").stdout.strip(), "acquired")

    def test_a_second_acquire_is_also_refused_not_renewed(self) -> None:
        """Renewing on re-acquire would let one process start two workers.

        The second delivery in the same subscriber is exactly the case the lease
        exists to stop, so it has to be refused; `renew()` is the explicit
        heartbeat for a caller that genuinely wants to extend.
        """
        lease = WorkerLease(self.db, ttl_seconds=60)
        self.addCleanup(lease.close)
        self.assertTrue(lease.acquire("node-1"))
        self.assertFalse(lease.acquire("node-1"))
        self.assertTrue(lease.renew("node-1"))

    def test_renew_refuses_after_release(self) -> None:
        lease = WorkerLease(self.db, ttl_seconds=60)
        self.addCleanup(lease.close)
        lease.acquire("node-1")
        lease.release("node-1")
        self.assertFalse(lease.renew("node-1"))

    def test_an_expired_lease_is_available_again(self) -> None:
        """A subscriber killed mid-run must not hold a node forever."""
        lease = WorkerLease(self.db, ttl_seconds=0.05, owner="first")
        self.addCleanup(lease.close)
        self.assertTrue(lease.acquire("node-1"))
        self.assertEqual(lease.holder("node-1"), "first")
        import time

        time.sleep(0.1)
        self.assertIsNone(lease.holder("node-1"), "an expired lease has no live holder")
        other = WorkerLease(self.db, owner="second")
        self.addCleanup(other.close)
        self.assertTrue(other.acquire("node-1"))

    def test_release_only_removes_your_own_row(self) -> None:
        lease = WorkerLease(self.db, owner="mine")
        self.addCleanup(lease.close)
        other = WorkerLease(self.db, owner="theirs")
        self.addCleanup(other.close)
        self.assertTrue(lease.acquire("node-1"))
        other.release("node-1")
        self.assertEqual(lease.holder("node-1"), "mine", "a different owner must not clear it")

    def test_reap_clears_expired_rows_only(self) -> None:
        lease = WorkerLease(self.db, ttl_seconds=0.05, owner="expiring")
        self.addCleanup(lease.close)
        live = WorkerLease(self.db, ttl_seconds=600, owner="live")
        self.addCleanup(live.close)
        lease.acquire("gone")
        live.acquire("kept")
        import time

        time.sleep(0.1)
        self.assertEqual(lease.reap(), 1)
        self.assertIsNone(lease.holder("gone"))
        self.assertEqual(live.holder("kept"), "live")


class _StubWorker:
    """A stand-in worker script: prints one JSON line, exits with a chosen code."""

    def __init__(self, directory: Path, *, status: str = "completed", returncode: int = 0, draft_id: str = "draft-9") -> None:
        self.path = directory / "stub_worker.py"
        self.path.write_text(
            "import json, sys\n"
            f"print(json.dumps({{'ran': 1, 'results': [{{'status': {status!r}, 'draft_id': {draft_id!r}}}]}}))\n"
            f"sys.exit({returncode})\n",
            encoding="utf-8",
        )

    def command(self) -> list[str]:
        return [sys.executable, str(self.path)]


class WorkerSubprocessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_a_successful_worker_reports_completed_and_its_draft_id(self) -> None:
        run = WorkerSubprocess(_StubWorker(self.tmp).command()).run("node-1:evt-1")
        self.assertEqual((run.status, run.returncode, run.draft_id), ("completed", 0, "draft-9"))

    def test_a_failing_worker_reports_the_last_stderr_line(self) -> None:
        worker = self.tmp / "failing.py"
        worker.write_text("import sys\nsys.stderr.write('boom: no key\\n')\nsys.exit(1)\n", encoding="utf-8")
        run = WorkerSubprocess([sys.executable, str(worker)]).run("node-1:evt-1")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.returncode, 1)
        self.assertIn("boom: no key", run.detail)

    def test_a_missing_executable_is_a_dispatch_error_not_a_failed_run(self) -> None:
        with self.assertRaises(WorkerDispatchError):
            WorkerSubprocess([str(self.tmp / "does-not-exist")]).run("node-1:evt-1")

    def test_a_hung_worker_times_out_and_leaves_the_row_for_replay(self) -> None:
        worker = self.tmp / "slow.py"
        worker.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        run = WorkerSubprocess([sys.executable, str(worker)], timeout_seconds=0.2).run("node-1:evt-1")
        self.assertEqual(run.status, "timeout")

    def test_the_default_command_points_at_the_shipped_worker(self) -> None:
        from work_agent_runtime.worker_dispatch import default_command

        command = default_command()
        self.assertTrue(Path(command[-1]).is_file(), command)
        self.assertEqual(Path(command[-1]).name, "main.py")

    def test_the_command_can_be_overridden_for_a_deployment(self) -> None:
        from work_agent_runtime.worker_dispatch import default_command

        previous = os.environ.get("SCIWEAVE_WORKER_COMMAND")
        os.environ["SCIWEAVE_WORKER_COMMAND"] = '["python3", "-m", "my.worker"]'
        try:
            self.assertEqual(default_command(), ["python3", "-m", "my.worker"])
            os.environ["SCIWEAVE_WORKER_COMMAND"] = "python3 -m my.worker"
            self.assertEqual(default_command(), ["python3", "-m", "my.worker"])
        finally:
            if previous is None:
                os.environ.pop("SCIWEAVE_WORKER_COMMAND", None)
            else:
                os.environ["SCIWEAVE_WORKER_COMMAND"] = previous

    def test_a_malformed_command_override_is_refused(self) -> None:
        from work_agent_runtime.worker_dispatch import default_command

        previous = os.environ.get("SCIWEAVE_WORKER_COMMAND")
        os.environ["SCIWEAVE_WORKER_COMMAND"] = "[not json"
        try:
            with self.assertRaises(WorkerDispatchError):
                default_command()
        finally:
            if previous is None:
                os.environ.pop("SCIWEAVE_WORKER_COMMAND", None)
            else:
                os.environ["SCIWEAVE_WORKER_COMMAND"] = previous

    def test_the_draft_id_is_read_from_the_workers_json_contract(self) -> None:
        stdout = "\n".join(
            [
                json.dumps({"agent": "researcher-task-agent", "workflows": []}),
                json.dumps({"ran": 1, "results": [{"status": "completed", "draft_id": "draft-42"}]}),
            ]
        )
        self.assertEqual(_draft_id_from(stdout), "draft-42")
        self.assertIsNone(_draft_id_from("not json at all"))
        self.assertIsNone(_draft_id_from(json.dumps({"ran": 0, "results": []})))


class ShippedWorkerEntryPointTests(unittest.TestCase):
    """The real `service-template/worker` process, not a stub.

    It is passed an unknown key so it takes the fast exit: the point is that the
    process starts, imports its dependencies and speaks the JSON contract, not
    that a model runs. A worker that cannot be started is the bug this ticket is
    about, so "it starts" is the assertion that matters.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.db = str(self.tmp / "inbox.sqlite3")

    def _run(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment.update(
            {
                "DATABASE_PATH": self.db,
                "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "1",
                "PYTHONPATH": str(RUNTIME_SRC),
            }
        )
        environment.update(env or {})
        return subprocess.run(
            [sys.executable, str(KIT_ROOT / "service-template" / "worker" / "src" / "main.py"), *args],
            capture_output=True,
            text=True,
            env=environment,
            timeout=60,
        )

    def test_the_worker_starts_and_reports_when_the_key_is_unknown(self) -> None:
        result = self._run("--dedupe-key", "node-1:evt-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(document["results"][0]["status"], "not_found")

    def test_the_worker_accepted_the_dedupe_key_argument(self) -> None:
        """Without `--dedupe-key` the shell would scan for queued rows instead."""
        result = self._run("--dedupe-key", "node-1:evt-1")
        self.assertNotIn("unrecognized arguments", result.stderr)
        self.assertIn("not_found", result.stdout)

    def test_the_worker_reports_an_invalid_configuration_as_a_startup_error(self) -> None:
        # Not the passthrough: that runtime has no configuration, so it returns
        # before the load. A real key path is what has to refuse a bad config.
        result = self._run(
            "--dedupe-key",
            "node-1:evt-1",
            env={
                "SCIWEAVE_AGENT_ID": "no-such-agent",
                "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "0",
                "DEEPSEEK_API_KEY": "sk-test",
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worker configuration is invalid", result.stderr)
        self.assertIn("no-such-agent", result.stderr)


class SubscriberCommitsBeforeTheWorkerTests(unittest.TestCase):
    """`run_loop` must not hold the offset until the model answers (ai4-0fwc).

    Holding it replays every message after a restart while the inbox dedupe
    blocks them all, which is strictly worse than committing and letting
    `drain_queued()` re-drive the queued rows.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = str(Path(self._tmp.name) / "kit.sqlite3")

    def test_the_offset_is_committed_even_though_the_worker_is_still_ahead(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "subscriber_main_commit",
            KIT_ROOT / "service-template" / "gateway" / "subscriber" / "src" / "main.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["subscriber_main_commit"] = module
        spec.loader.exec_module(module)

        from work_agent_runtime import FakeQueue, QueueMessage

        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        dispatcher = _Recorder(status="failed")  # the worker did not finish
        runtime = WorkAgentRuntime(inbox=inbox, dispatcher=dispatcher)
        runtime.lease = WorkerLease(self.db)
        self.addCleanup(runtime.lease.close)

        queue = FakeQueue()
        queue.messages = [
            QueueMessage(
                topic="t",
                partition=0,
                offset=1,
                key="node-1:cv-1",
                payload={"message_type": "task_handoff_ready", "task_node_id": "node-1"},
            )
        ]
        processed = module.run_loop(runtime, queue, ["t"], max_messages=1, agent_id="researcher-1")
        self.assertEqual(processed, 1)
        self.assertTrue(queue.committed, "the offset must not wait for the worker")
        self.assertEqual(inbox.get("node-1:node-1:cv-1")["status"], "queued", "the row stays replayable")


if __name__ == "__main__":
    unittest.main()
