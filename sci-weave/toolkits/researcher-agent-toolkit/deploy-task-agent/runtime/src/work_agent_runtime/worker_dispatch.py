"""Dispatch one handoff to a short-lived worker process (ai4-0fwc).

ADR-0002 puts the model loop in a **short-lived worker process** that the
subscriber starts; `docs/data-flow/work-agent.md` says the same. The code did
not: `run_one()` ran inline in the subscriber, so the resident process needed
the model credentials and blocked on a long model call while the partition
stalled. `service-template/worker` had the right shape but nothing started it.

This module is the missing edge. The subscriber owns the queue and the durable
inbox; the worker owns the model and the draft-box credential, and exits.

**What the offset means now.** The subscriber commits after the inbox row is
durable, not after the model answers. That is the only rule that holds when the
work outlives the poll loop: a crash between commit and completion leaves a
``queued`` inbox row, and `drain_queued()` re-drives it on the next start. The
alternative — holding the offset until the model finishes — replays every
message after a restart while the inbox dedupe blocks them all, which is what
the old code did.

**Why the worker is invoked with an explicit key.** Letting the worker scan
``queued`` rows would race two subscribers for the same row. The subscriber has
already claimed the row under the Worker Lease; it passes that one key and the
worker takes only it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 1800.0


@dataclass(frozen=True)
class WorkerRun:
    """The outcome of one worker subprocess."""

    dedupe_key: str
    status: str
    returncode: int | None = None
    detail: str = ""
    draft_id: str | None = None

    @property
    def completed(self) -> bool:
        return self.status == "completed"


def _draft_id_from(stdout: str) -> str | None:
    """Pull the draft id out of the worker's last JSON line.

    The worker prints one JSON object per line: the configuration it loaded,
    then ``{"ran": ..., "results": [...]}``. Parsing the contracts the worker
    already prints beats inventing a second protocol just for this.
    """
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        for result in document.get("results") or ():
            if isinstance(result, dict) and result.get("draft_id"):
                return str(result["draft_id"])
    return None


class WorkerDispatchError(RuntimeError):
    """The worker could not be started at all (as opposed to failing to run)."""


def default_command() -> list[str]:
    """The command that runs one worker.

    ``sys.executable`` rather than ``uv run``: the subscriber is already running
    inside the runtime project's environment, so the subprocess inherits an
    interpreter that can import `work_agent_runtime`. Re-resolving through uv on
    every message would pay a lock check per handoff for no benefit.

    ``SCIWEAVE_WORKER_COMMAND`` overrides it (a shell-free JSON list or a plain
    string, split on whitespace), which is how a deployment can point at its own
    wrapper without patching the kit.
    """
    configured = os.environ.get("SCIWEAVE_WORKER_COMMAND", "").strip()
    if configured:
        if configured.startswith("["):
            try:
                command = json.loads(configured)
            except json.JSONDecodeError as error:
                raise WorkerDispatchError(f"SCIWEAVE_WORKER_COMMAND is not valid JSON: {error}") from error
            if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
                raise WorkerDispatchError("SCIWEAVE_WORKER_COMMAND must be a JSON list of strings")
            return command
        return configured.split()

    kit = Path(__file__).resolve().parents[3]
    main = kit / "service-template" / "worker" / "src" / "main.py"
    return [sys.executable, str(main)]


class LeaveQueued:
    """A dispatcher that deliberately runs nothing.

    This is what `SCIWEAVE_WORKER_DISPATCH=0` installs. Returning None from
    `build_dispatcher` instead would fall back to the inline path, which writes
    a fabricated draft and marks the row processed — the opposite of "the two
    roles are separate services". Deferring keeps the row durable so the
    standalone worker can pick it up.
    """

    #: Read by `WorkAgentRuntime._dispatch` before it starts anything.
    deferred = True

    def __call__(self, dedupe_key: str) -> WorkerRun:
        return WorkerRun(dedupe_key, "queued", None, "worker dispatch is disabled in this process")


class WorkerSubprocess:
    """Start one worker process for one handoff, and wait for it.

    Waiting is correct here: the subscriber holds the lease for the target while
    the worker runs, and the lease is what stops a second delivery from starting
    a competing worker. A single subscriber therefore processes handoffs
    serially — which is what a per-target lease means anyway.
    """

    def __init__(self, command: list[str] | None = None, *, timeout_seconds: float | None = None) -> None:
        self.command = list(command) if command is not None else default_command()
        if not self.command:
            raise WorkerDispatchError("the worker command is empty")
        if timeout_seconds is None:
            timeout_seconds = float(os.environ.get("SCIWEAVE_WORKER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        self.timeout_seconds = float(timeout_seconds)

    def __call__(self, dedupe_key: str) -> WorkerRun:
        """A dispatcher is any callable taking the claimed row's key."""
        return self.run(dedupe_key)

    def run(self, dedupe_key: str) -> WorkerRun:
        try:
            completed = subprocess.run(
                [*self.command, "--dedupe-key", dedupe_key],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=dict(os.environ),
            )
        except FileNotFoundError as error:
            raise WorkerDispatchError(f"cannot start the worker: {error}") from error
        except subprocess.TimeoutExpired:
            # The row stays ``queued``; the lease expires and the next start
            # re-drives it. Killing the process is the timeout's own doing.
            return WorkerRun(dedupe_key, "timeout", None, f"exceeded {self.timeout_seconds:g}s")
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            return WorkerRun(
                dedupe_key,
                "failed",
                completed.returncode,
                detail[-1] if detail else f"exit {completed.returncode}",
            )
        stdout = completed.stdout or ""
        return WorkerRun(dedupe_key, "completed", 0, stdout.strip(), _draft_id_from(stdout))
