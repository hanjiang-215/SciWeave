"""T2 基线执行的行为测试（ai4-j7g2）。

测试缝：``main()`` 打印的记录字典与退出码。测试不触碰 KNN 内部实现，
只断言证据可核验所需的两件事：输入哈希来自实测，且哈希不符时不产出指标。
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

EVIDENCE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT = EVIDENCE_DIR / "iris_data.csv"
FAILURE_FIXTURE = EVIDENCE_DIR / "iris_data_failure_inject.csv"


def load_script():
    spec = importlib.util.spec_from_file_location("run_iris_baseline", EVIDENCE_DIR / "run_iris_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunIrisBaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)

    def _run(self, path: Path) -> tuple[int, dict]:
        buffer = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_iris_baseline.py", str(path)]), redirect_stdout(buffer):
            code = self.script.main()
        return code, json.loads(buffer.getvalue())

    def test_reports_the_measured_hash_of_the_pinned_snapshot(self) -> None:
        code, record = self._run(SNAPSHOT)

        self.assertEqual(code, 0)
        self.assertEqual(record["input_snapshot_sha256"],
                         "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4")

    def test_the_reported_hash_follows_the_file_not_a_constant(self) -> None:
        pinned = SNAPSHOT.read_bytes()
        copied = self.tmp / "renamed.csv"
        copied.write_bytes(pinned)

        _, record = self._run(copied)

        self.assertEqual(record["input_snapshot_sha256"],
                         "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4")

    def test_crlf_copy_reports_the_same_hash(self) -> None:
        crlf = self.tmp / "crlf.csv"
        crlf.write_bytes(SNAPSHOT.read_bytes().replace(b"\n", b"\r\n"))

        code, record = self._run(crlf)

        self.assertEqual(code, 0)
        self.assertEqual(record["input_snapshot_sha256"],
                         "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4")

    def test_altered_content_fails_without_producing_metrics(self) -> None:
        tampered = self.tmp / "tampered.csv"
        tampered.write_bytes(SNAPSHOT.read_bytes().replace(b"5.1,3.5,1.4,0.2", b"5.2,3.5,1.4,0.2", 1))

        code, record = self._run(tampered)

        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["reason_code"], "source_hash_mismatch")
        self.assertNotIn("accuracy", record)
        self.assertNotIn("confusion_matrix", record)

    def test_still_reproduces_the_pinned_baseline(self) -> None:
        code, record = self._run(SNAPSHOT)

        self.assertEqual(code, 0)
        self.assertEqual(record["accuracy"], 0.955556)
        self.assertEqual(record["test_size"], 45)
        self.assertEqual(sum(sum(row.values()) for row in record["confusion_matrix"].values()), 45)

    def test_missing_class_column_fails_without_producing_metrics(self) -> None:
        code, record = self._run(FAILURE_FIXTURE)

        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["reason_code"], "missing_columns", record)
        self.assertNotIn("accuracy", record)


if __name__ == "__main__":
    unittest.main()
