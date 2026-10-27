from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from sciencepal_bridge.client import RunHandle, RunState, SandboxFile
from sciencepal_bridge.config import BridgeConfig, ConfigError
from sciencepal_bridge.service import SciencePalService
from sciencepal_bridge.store import RunStore


class FakeSciencePalClient:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = files or {}
        self.initiate_calls: list[dict[str, object]] = []
        self.state = "queued"
        self.stopped = False
        self.listed_dirs: list[str] = []

    def initiate(self, **kwargs: object) -> RunHandle:
        self.initiate_calls.append(kwargs)
        return RunHandle(run_id="run-1", thread_id="thread-1")

    def get_run(self, run_id: str) -> RunState:
        return RunState(
            run_id=run_id,
            thread_id="thread-1",
            status=self.state,
            error=None,
            started_at=None,
            completed_at=None,
        )

    def stop_run(self, run_id: str) -> bool:
        self.stopped = True
        return True

    def get_sandbox_id(self, thread_id: str) -> str:
        return "sandbox-1"

    def list_files(self, sandbox_id: str, path: str = "/") -> list[SandboxFile]:
        self.listed_dirs.append(path)
        if path == "/":
            return [SandboxFile("outputs", "/outputs", True, 0, None)]
        if path in {"/outputs", "/workspace/outputs"}:
            return [
                SandboxFile(name, f"{path}/{name}", False, len(content), None)
                for name, content in self.files.items()
            ]
        return []

    def read_file(self, sandbox_id: str, path: str) -> bytes:
        return self.files[path.rsplit("/", 1)[-1]]

    def list_agents(self) -> list[dict[str, object]]:
        return [{"id": "agent-general", "name": "General"}]


def make_config(workspace: Path, *, token: str = "test-token") -> BridgeConfig:
    return BridgeConfig(
        base_url="https://sciencepal.ai/api",
        access_token=token,
        workspace=workspace,
        run_db=workspace / "runs.sqlite",
        max_upload_bytes=1024 * 1024,
        max_download_bytes=10 * 1024 * 1024,
        max_artifacts=10,
        request_timeout_s=5.0,
        default_agent_id=None,
    )


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "workspace"
        self.workspace.mkdir()
        self.config = make_config(self.workspace)
        self.store = RunStore(self.config.run_db)
        self.client = FakeSciencePalClient({"report.md": b"# report\n", "result.json": b'{"ok": true}'})
        self.service = SciencePalService(self.config, client=self.client, store=self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_start_is_idempotent(self) -> None:
        first = self.service.start(instruction="run T1", idempotency_key="exec-1")
        second = self.service.start(instruction="run T1", idempotency_key="exec-1")
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(len(self.client.initiate_calls), 1)

    def test_start_rejects_paths_outside_workspace(self) -> None:
        outside = Path(self.temp.name) / "outside.csv"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "workspace_violation"):
            self.service.start(
                instruction="run",
                idempotency_key="exec-outside",
                files=[{"path": str(outside)}],
            )

    def test_start_hashes_inputs(self) -> None:
        source = self.workspace / "iris.csv"
        source.write_bytes(b"a,b\n1,2\n")
        result = self.service.start(
            instruction="run",
            idempotency_key="exec-hash",
            files=[{"path": str(source)}],
        )
        self.assertEqual(result["inputs"][0]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(result["inputs"][0]["name"], "iris.csv")

    def test_status_updates_ledger(self) -> None:
        started = self.service.start(instruction="run", idempotency_key="exec-status")
        self.client.state = "running"
        status = self.service.status(started["run_id"])
        self.assertEqual(status["status"], "running")
        self.assertFalse(status["terminal"])
        self.assertEqual(self.store.get(started["run_id"])["status"], "running")

    def test_collect_downloads_and_hashes(self) -> None:
        started = self.service.start(instruction="run", idempotency_key="exec-collect")
        self.store.update_status(started["run_id"], "completed")
        result = self.service.collect(started["run_id"])
        self.assertEqual(result["reused"], False)
        self.assertEqual(len(result["artifacts"]), 2)
        report = next(item for item in result["artifacts"] if item["name"] == "report.md")
        self.assertEqual(report["kind"], "report")
        downloaded = self.workspace / "runs" / "run-1" / "report.md"
        self.assertEqual(downloaded.read_bytes(), b"# report\n")
        self.assertEqual(report["sha256"], hashlib.sha256(b"# report\n").hexdigest())
        self.assertTrue(Path(result["manifest_path"]).is_file())

    def test_collect_deduplicates_mirrored_outputs(self) -> None:
        started = self.service.start(instruction="run", idempotency_key="exec-dedupe")
        self.store.update_status(started["run_id"], "completed")
        result = self.service.collect(started["run_id"])
        self.assertEqual(len(result["artifacts"]), 2)
        self.assertEqual(len(result["skipped"]), 2)
        self.assertTrue(all(item["reason"] == "duplicate" for item in result["skipped"]))
        self.assertEqual({item["path"] for item in result["artifacts"]}, {"report.md", "result.json"})

    def test_collect_requires_completed_run(self) -> None:
        started = self.service.start(instruction="run", idempotency_key="exec-running")
        with self.assertRaisesRegex(Exception, "sciencepal_run_not_completed"):
            self.service.collect(started["run_id"])

    def test_cancel_terminal_run_is_not_accepted(self) -> None:
        started = self.service.start(instruction="run", idempotency_key="exec-cancel")
        self.store.update_status(started["run_id"], "completed")
        result = self.service.cancel(started["run_id"])
        self.assertFalse(result["accepted"])
        self.assertFalse(self.client.stopped)

    def test_list_agents_returns_ids(self) -> None:
        result = self.service.list_agents()
        self.assertEqual(result["agents"][0]["id"], "agent-general")


class ConfigTests(unittest.TestCase):
    def test_requires_token_on_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), token="")
            service = SciencePalService(config, client=FakeSciencePalClient())
            with self.assertRaisesRegex(Exception, "sciencepal_token_missing"):
                service.start(instruction="run", idempotency_key="exec-no-token")

    def test_rejects_non_https_base_url(self) -> None:
        with self.assertRaises(ConfigError):
            BridgeConfig.from_env(
                {
                    "SCIENCEPAL_BASE_URL": "http://sciencepal.ai/api",
                    "SCIENCEPAL_ACCESS_TOKEN": "t",
                }
            )

    def test_defaults_workspace_and_run_db(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = BridgeConfig.from_env(
                {
                    "SCIENCEPAL_ACCESS_TOKEN": "t",
                    "SCIENCEPAL_WORKSPACE": directory,
                }
            )
            self.assertEqual(config.run_db, Path(directory).resolve() / "runs.sqlite")


if __name__ == "__main__":
    unittest.main()
