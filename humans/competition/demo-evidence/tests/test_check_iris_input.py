"""T1 输入检查的行为测试（ai4-483l）。

测试缝：``check(path)`` 返回的记录字典，以及 ``main()`` 的退出码。
两者都是脚本的公开界面，测试不触碰 ``sha256_of`` 等内部实现。
"""
from __future__ import annotations

import importlib.util
import io
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
    spec = importlib.util.spec_from_file_location("check_iris_input", EVIDENCE_DIR / "check_iris_input.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckIrisInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)

    def _write(self, name: str, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def test_pinned_snapshot_passes(self) -> None:
        record = self.script.check(SNAPSHOT)

        self.assertEqual(record["status"], "ok", record)
        self.assertEqual(record["row_count"], 150)
        self.assertEqual(record["class_counts"], {"Iris-setosa": 50, "Iris-versicolor": 50, "Iris-virginica": 50})

    def test_crlf_copy_of_the_same_content_passes(self) -> None:
        pinned = SNAPSHOT.read_bytes()
        crlf = pinned.replace(b"\n", b"\r\n")
        self.assertNotEqual(crlf, pinned, "fixture must differ byte-wise from the pinned snapshot")

        record = self.script.check(self._write("crlf.csv", crlf))

        self.assertEqual(record["status"], "ok", record)
        self.assertEqual(record["snapshot_sha256"], self.script.check(SNAPSHOT)["snapshot_sha256"])

    def test_missing_class_column_reports_missing_columns(self) -> None:
        record = self.script.check(FAILURE_FIXTURE)

        self.assertEqual(record["status"], "failed", record)
        self.assertEqual(record["reason_code"], "missing_columns", record)

    def test_changed_values_with_every_column_present_is_a_hash_mismatch(self) -> None:
        pinned = SNAPSHOT.read_bytes()
        tampered = pinned.replace(b"5.1,3.5,1.4,0.2", b"5.2,3.5,1.4,0.2", 1)
        self.assertNotEqual(tampered, pinned)

        record = self.script.check(self._write("tampered.csv", tampered))

        self.assertEqual(record["status"], "failed", record)
        self.assertEqual(record["reason_code"], "source_hash_mismatch", record)

    def test_cli_exits_zero_when_the_check_passes(self) -> None:
        self.assertEqual(self._run_cli(SNAPSHOT), 0)

    def test_cli_exits_one_when_the_check_fails(self) -> None:
        self.assertEqual(self._run_cli(FAILURE_FIXTURE), 1)

    def _run_cli(self, path: Path) -> int:
        with mock.patch.object(sys, "argv", ["check_iris_input.py", str(path)]), redirect_stdout(io.StringIO()):
            return self.script.main()


if __name__ == "__main__":
    unittest.main()
