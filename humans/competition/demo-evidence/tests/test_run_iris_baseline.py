"""T2 基线执行的行为测试（ai4-j7g2）。

测试缝：``main()`` 打印的记录字典与退出码。测试不触碰 KNN 内部实现，
只断言证据可核验所需的两件事：输入哈希来自实测，且哈希不符时不产出指标。
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from support import FAILURE_FIXTURE, PINNED_SHA256, SNAPSHOT, load_script


class RunIrisBaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script("run_iris_baseline")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)

    def _write(self, name: str, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def _run(self, path: Path) -> tuple[int, dict]:
        buffer = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_iris_baseline.py", str(path)]), redirect_stdout(buffer):
            code = self.script.main()
        return code, json.loads(buffer.getvalue())

    def test_reports_the_measured_hash_of_the_pinned_snapshot(self) -> None:
        code, record = self._run(SNAPSHOT)

        self.assertEqual(code, 0)
        self.assertEqual(record["input_snapshot_sha256"], PINNED_SHA256)

    def test_the_reported_hash_is_measured_not_echoed_from_the_constant(self) -> None:
        """把期望值换成一个不同的哈希，输出必须仍是文件的实际哈希。

        若实现退回「直接打印常量」，这条会在输入合法的前提下报出那个假值。
        """
        pinned = SNAPSHOT.read_bytes()
        copied = self._write("renamed.csv", pinned)

        with mock.patch.object(self.script, "EXPECTED_SHA256", "0" * 64):
            code, record = self._run(copied)

        self.assertEqual(code, 1)
        self.assertEqual(record["reason_code"], "source_hash_mismatch")
        self.assertEqual(record["detail"]["observed_sha256"], PINNED_SHA256)
        self.assertEqual(record["detail"]["expected_sha256"], "0" * 64)

    def test_crlf_copy_reports_the_same_hash(self) -> None:
        crlf = self._write("crlf.csv", SNAPSHOT.read_bytes().replace(b"\n", b"\r\n"))

        code, record = self._run(crlf)

        self.assertEqual(code, 0)
        self.assertEqual(record["input_snapshot_sha256"], PINNED_SHA256)

    def test_altered_content_fails_without_producing_metrics(self) -> None:
        tampered = self._write("tampered.csv",
                               SNAPSHOT.read_bytes().replace(b"5.1,3.5,1.4,0.2", b"5.2,3.5,1.4,0.2", 1))

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
        self.assertEqual(record["reason_code"], "missing_columns", record)
        self.assertNotIn("accuracy", record)

    def test_non_numeric_feature_is_reported_not_raised(self) -> None:
        corrupted = self._write("corrupt.csv",
                                SNAPSHOT.read_bytes().replace(b"5.1,3.5,1.4,0.2", b"nope,3.5,1.4,0.2", 1))

        code, record = self._run(corrupted)

        self.assertEqual(code, 1)
        self.assertEqual(record["reason_code"], "invalid_values", record)
        self.assertNotIn("accuracy", record)

    def test_missing_file_is_reported_not_raised(self) -> None:
        code, record = self._run(self.tmp / "absent.csv")

        self.assertEqual(code, 1)
        self.assertEqual(record["reason_code"], "unreadable_input", record)


if __name__ == "__main__":
    unittest.main()
