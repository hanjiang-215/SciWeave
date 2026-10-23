"""Worker runtime configuration tests; values are synthetic and credential-free."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from task_agent_worker.config import WorkerSettings


class WorkerSettingsTests(unittest.TestCase):
    def test_requires_paths_from_environment(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SCIWEAVE_WORKER_HOME"):
                WorkerSettings.from_environment()

    def test_rejects_session_directory_escape(self) -> None:
        values = {
            "SCIWEAVE_WORKER_HOME": "runtime-home",
            "SCIWEAVE_WORKER_SESSION_DIR": "../outside",
            "SCIWEAVE_WORKER_CONNECTION_SCOPE": "task-agent",
        }
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaisesRegex(ValueError, "stay within Worker home"):
                WorkerSettings.from_environment().validate_runtime(require_api_key=False)

    def test_accepts_explicit_safe_runtime_paths_without_model_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = {
                "SCIWEAVE_WORKER_HOME": str(Path(temp_dir) / "worker-home"),
                "SCIWEAVE_WORKER_SESSION_DIR": "sessions",
                "SCIWEAVE_WORKER_CONNECTION_SCOPE": "task-agent",
            }
            with patch.dict(os.environ, values, clear=True):
                settings = WorkerSettings.from_environment()
                settings.validate_runtime(require_api_key=False)
                self.assertEqual(settings.home, Path(values["SCIWEAVE_WORKER_HOME"]))
                self.assertEqual(settings.session_dir, "sessions")

    def test_rejects_placeholder_api_key(self) -> None:
        values = {
            "DEEPSEEK_API_KEY": "replace-with-placeholder",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "SCIWEAVE_WORKER_MODEL": "deepseek-chat",
            "SCIWEAVE_WORKER_HOME": "runtime-home",
            "SCIWEAVE_WORKER_SESSION_DIR": "sessions",
            "SCIWEAVE_WORKER_CONNECTION_SCOPE": "task-agent",
        }
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                WorkerSettings.from_environment().validate_for_model_call()


if __name__ == "__main__":
    unittest.main()
