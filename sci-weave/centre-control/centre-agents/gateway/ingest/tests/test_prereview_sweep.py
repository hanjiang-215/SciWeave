"""The stalled-consumer sweeper, exercised as the operator runs it (ai4-0wg0).

The sweeper used to ship inside the centre suite, which is gone; it now lives in
``centre-agents/ops/``. These tests run the script itself rather than a Python
reimplementation of it: the whole point of the file is its exit code, and a
ported copy would pass tests the shell script fails.

Exit codes are the contract: 0 healthy, 1 stalled or unreachable, 2 misconfigured.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CENTRE_AGENTS = Path(__file__).resolve().parents[3]
SWEEPER = CENTRE_AGENTS / "ops" / "prereview-sweep.sh"

SCHEMA = """
CREATE TABLE processed_events (
    dedupe_key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('processed', 'error')),
    reason TEXT,
    handled_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def seed(path: Path, *, handled_at: str | None, status: str = "processed") -> None:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    if handled_at is not None:
        connection.execute(
            "INSERT INTO processed_events (dedupe_key, status, handled_at) VALUES (?, ?, ?)",
            ("map-1:cand-1:head-1", status, handled_at),
        )
    connection.commit()
    connection.close()


@unittest.skipUnless(shutil.which("sh"), "the sweeper is a POSIX shell script")
class SweeperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "ingest.sqlite3"

    def run_sweeper(self, **environment: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("SCIWEAVE_")}
        env.update(environment)
        return subprocess.run(
            ["sh", str(SWEEPER)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_a_missing_database_is_not_configured(self) -> None:
        # Exit 2, not 1: "I cannot tell" and "it is stalled" send the operator
        # to different places, and a sweeper that cries stall on a fresh host
        # gets muted within a day.
        result = self.run_sweeper(SCIWEAVE_INGEST_DB=str(self.db))
        self.assertEqual(result.returncode, 2)
        self.assertIn("SCIWEAVE_INGEST_DB", result.stderr)

    def test_an_empty_table_is_not_a_stall(self) -> None:
        seed(self.db, handled_at=None)
        result = self.run_sweeper(SCIWEAVE_INGEST_DB=str(self.db))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not yet exercised", result.stdout)

    def test_a_recent_commit_is_healthy(self) -> None:
        seed(self.db, handled_at=utc_now())
        result = self.run_sweeper(SCIWEAVE_INGEST_DB=str(self.db))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ingest alive", result.stdout)

    def test_an_old_commit_is_a_stall(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0)
        seed(self.db, handled_at=stale.isoformat().replace("+00:00", "Z"))
        result = self.run_sweeper(SCIWEAVE_INGEST_DB=str(self.db))
        self.assertEqual(result.returncode, 1)
        self.assertIn("stalled", result.stderr)

    def test_the_age_limit_is_configurable(self) -> None:
        recent = (datetime.now(timezone.utc) - timedelta(seconds=30)).replace(microsecond=0)
        seed(self.db, handled_at=recent.isoformat().replace("+00:00", "Z"))
        result = self.run_sweeper(
            SCIWEAVE_INGEST_DB=str(self.db),
            SCIWEAVE_PREREVIEW_SWEEP_MAX_AGE_SECONDS="5",
        )
        self.assertEqual(result.returncode, 1, "a 5 second limit must not accept a 30 second old row")

    def test_an_error_row_still_counts_as_activity(self) -> None:
        # errors are recorded, not swallowed: a consumer that keeps failing is
        # alive, and the last status is printed so the operator can see why.
        seed(self.db, handled_at=utc_now(), status="error")
        result = self.run_sweeper(SCIWEAVE_INGEST_DB=str(self.db))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("error", result.stdout)


class _Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        code = 200 if self.path == "/health" else 404
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        return


@unittest.skipUnless(shutil.which("sh") and shutil.which("curl"), "needs sh and curl")
class DomainHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "ingest.sqlite3"
        seed(self.db, handled_at=utc_now())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def run_sweeper(self, **environment: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("SCIWEAVE_")}
        env.pop("RESEARCH_MAPPING_MCP_URL", None)
        env.pop("LLM_WIKI_MCP_URL", None)
        env.update(environment)
        return subprocess.run(
            ["sh", str(SWEEPER)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_both_domains_get_probed(self) -> None:
        # Mapping and Wiki are separate services: one answering says nothing
        # about the other, so a single probe would let a dead domain through.
        result = self.run_sweeper(
            SCIWEAVE_INGEST_DB=str(self.db),
            RESEARCH_MAPPING_MCP_URL=self.url,
            LLM_WIKI_MCP_URL=self.url,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("domain MCP reachable"), 2)

    def test_one_dead_domain_fails_the_sweep(self) -> None:
        dead = f"http://127.0.0.1:{self.server.server_port}/missing/mcp"
        result = self.run_sweeper(
            SCIWEAVE_INGEST_DB=str(self.db),
            RESEARCH_MAPPING_MCP_URL=self.url,
            LLM_WIKI_MCP_URL=dead,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("/missing/health", result.stderr)

    def test_an_explicit_url_list_overrides_the_cards(self) -> None:
        result = self.run_sweeper(
            SCIWEAVE_INGEST_DB=str(self.db),
            SCIWEAVE_PREREVIEW_SWEEP_MCP_URLS=self.url,
            RESEARCH_MAPPING_MCP_URL="http://127.0.0.1:1/never",
            LLM_WIKI_MCP_URL="http://127.0.0.1:1/never",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("domain MCP reachable"), 1)
