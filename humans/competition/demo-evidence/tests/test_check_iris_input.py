"""T1 输入检查的行为测试（ai4-483l）。

测试缝：``check(path)`` 返回的记录字典，以及 ``main()`` 的退出码。
两者都是脚本的公开界面，测试不触碰 ``sha256_of`` 等内部实现。
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from support import EVIDENCE_DIR, FAILURE_FIXTURE, PINNED_SHA256, SNAPSHOT, STALE_SHA256, load_script


class CheckIrisInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script("check_iris_input")
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
        self.assertEqual(record["snapshot_sha256"], PINNED_SHA256)

    def test_crlf_copy_of_the_same_content_passes(self) -> None:
        pinned = SNAPSHOT.read_bytes()
        crlf = pinned.replace(b"\n", b"\r\n")
        self.assertNotEqual(crlf, pinned, "fixture must differ byte-wise from the pinned snapshot")

        record = self.script.check(self._write("crlf.csv", crlf))

        self.assertEqual(record["status"], "ok", record)
        self.assertEqual(record["snapshot_sha256"], PINNED_SHA256)

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

    def test_row_count_failure_is_reported_as_such_not_as_a_hash_mismatch(self) -> None:
        lines = SNAPSHOT.read_bytes().splitlines(keepends=True)
        truncated = b"".join(lines[:-1])

        record = self.script.check(self._write("short.csv", truncated))

        self.assertEqual(record["reason_code"], "row_count_mismatch", record)

    def test_class_count_failure_is_reported_as_such_not_as_a_hash_mismatch(self) -> None:
        renamed = SNAPSHOT.read_bytes().replace(b"Iris-virginica", b"Iris-virginica-x")

        record = self.script.check(self._write("renamed.csv", renamed))

        self.assertEqual(record["reason_code"], "class_count_mismatch", record)

    def test_missing_value_is_reported_as_such_not_as_a_hash_mismatch(self) -> None:
        blanked = SNAPSHOT.read_bytes().replace(b"5.1,3.5,1.4,0.2", b",3.5,1.4,0.2", 1)

        record = self.script.check(self._write("blank.csv", blanked))

        self.assertEqual(record["reason_code"], "missing_values", record)

    def test_undecodable_input_is_reported_not_raised(self) -> None:
        undecodable = self._write("utf16.csv", SNAPSHOT.read_bytes().decode("utf-8").encode("utf-16"))

        record = self.script.check(undecodable)

        self.assertEqual(record["status"], "failed", record)
        self.assertEqual(record["reason_code"], "unreadable_input", record)

    def test_missing_file_is_reported_not_raised(self) -> None:
        record = self.script.check(self.tmp / "absent.csv")

        self.assertEqual(record["reason_code"], "unreadable_input", record)

    def test_cli_exits_zero_when_the_check_passes(self) -> None:
        self.assertEqual(self._run_cli(SNAPSHOT), 0)

    def test_cli_exits_one_when_the_check_fails(self) -> None:
        self.assertEqual(self._run_cli(FAILURE_FIXTURE), 1)

    def _run_cli(self, path: Path) -> int:
        with mock.patch.object(sys, "argv", ["check_iris_input.py", str(path)]), redirect_stdout(io.StringIO()):
            return self.script.main()

    def test_pinned_hash_is_consistent_across_every_documented_copy(self) -> None:
        """快照哈希以字面量散落在五个文件里，收紧成「都提到新值、没有一处留旧值」。

        文档里用的是缩写形式（`ea110d42...b6f9f4`），所以按前后缀分别比对。
        """
        documents = {
            "check_iris_input.py": EVIDENCE_DIR / "check_iris_input.py",
            "run_iris_baseline.py": EVIDENCE_DIR / "run_iris_baseline.py",
            "README.md": EVIDENCE_DIR / "README.md",
            "evidence-card.md": EVIDENCE_DIR / "evidence-card.md",
            "t2-baseline-agent.md": EVIDENCE_DIR.parent / "sciencpal-onboarding" / "agent" / "t2-baseline-agent.md",
        }
        for label, path in documents.items():
            text = path.read_text(encoding="utf-8")
            with self.subTest(document=label):
                self.assertIn(PINNED_SHA256[:8], text, f"{label} 未引用当前快照哈希")
                self.assertIn(PINNED_SHA256[-6:], text, f"{label} 的长摘要被截断成别的值")
                self.assertNotIn(STALE_SHA256[:8], text, f"{label} 仍引用行尾未归一化的旧哈希")
                self.assertNotIn(STALE_SHA256[-6:], text, f"{label} 仍引用旧哈希的长摘要")


if __name__ == "__main__":
    unittest.main()