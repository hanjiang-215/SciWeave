from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from draft_buffer.main import main


class DemoShortCircuitTests(unittest.TestCase):
    """`SCIWEAVE_BUFFER_DEMO=1` 只做自检输出，绝不能被读成「草稿箱已就绪」。"""

    def test_demo_switch_reports_stub_and_never_claims_readiness(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"SCIWEAVE_BUFFER_DEMO": "1"}):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main()
        report = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "stub")
        self.assertFalse(report["serving"])
        self.assertEqual(report["reason_code"], "buffer_demo_short_circuit")
        self.assertNotEqual(report["status"], "ready")

    def test_demo_switch_warns_on_stderr_that_no_service_runs(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"SCIWEAVE_BUFFER_DEMO": "1"}):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main()
        self.assertIn("不提供任何草稿箱服务", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
