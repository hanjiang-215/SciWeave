#!/usr/bin/env python3
"""T1 固定并检查输入：验证 UCI Iris 官方 CSV 快照的完整性与来源。

只使用 Python 标准库，输出可核验的 JSON 检查记录。这是 `ai4-aaff`
（SciWeave 默认科研示例场景）中 T1 任务的验收脚本：缺列、类别计数
不符或来源快照哈希不符时失败并留下原因，不生成后续分析产物。
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_SHA256 = "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4"
EXPECTED_ROWS = 150
EXPECTED_FEATURE_COLUMNS = ("sepal length", "sepal width", "petal length", "petal width")
EXPECTED_CLASS_COLUMN = "class"
EXPECTED_CLASS_COUNTS = {"Iris-setosa": 50, "Iris-versicolor": 50, "Iris-virginica": 50}
SOURCE = "https://archive.ics.uci.edu/static/public/53/data.csv"
DOI = "10.24432/C56C76"
LICENSE = "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/legalcode)"


def sha256_of(path: Path) -> str:
    """Hash the snapshot content, not the working copy's line endings.

    The official CSV ships with CRLF, while this repository stores it with LF.
    A checkout therefore differs byte-wise from the published file even though
    nothing changed. Normalising before hashing keeps the provenance check
    meaningful across Git's line-ending policy (``ai4-483l``).
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check(path: Path) -> dict[str, object]:
    """Structural checks first, provenance last.

    Every reason code stays reachable: any file that passes the hash *is* the
    pinned snapshot, so a hash check placed earlier would silently swallow the
    row-count, missing-value and class-count failures. Provenance still gates
    success — it just speaks last, after the more specific diagnosis.
    """
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            if set(EXPECTED_FEATURE_COLUMNS) - set(columns) or EXPECTED_CLASS_COLUMN not in columns:
                return _failed("missing_columns", {"columns": columns})
            rows = list(reader)
    except UnicodeDecodeError:
        return _failed("unreadable_input", {"reason": "not valid UTF-8"})
    except OSError as error:
        return _failed("unreadable_input", {"reason": str(error)})

    if len(rows) != EXPECTED_ROWS:
        return _failed("row_count_mismatch", {"observed": len(rows), "expected": EXPECTED_ROWS})

    missing = 0
    class_counts: dict[str, int] = {}
    malformed = []
    for index, row in enumerate(rows, start=2):
        values = [row.get(column) for column in EXPECTED_FEATURE_COLUMNS]
        parsed = []
        for value in values:
            try:
                parsed.append(float(value))
            except (TypeError, ValueError):
                parsed.append(None)
        if any(value is None for value in parsed) or not row.get(EXPECTED_CLASS_COLUMN):
            missing += 1
            if len(malformed) < 5:
                malformed.append(index)
        label = row.get(EXPECTED_CLASS_COLUMN, "")
        class_counts[label] = class_counts.get(label, 0) + 1

    if missing:
        return _failed("missing_values", {"missing_rows": missing, "sample_line_numbers": malformed})
    if class_counts != EXPECTED_CLASS_COUNTS:
        return _failed("class_count_mismatch", {"observed": class_counts, "expected": EXPECTED_CLASS_COUNTS})

    observed_sha256 = sha256_of(path)
    if observed_sha256 != EXPECTED_SHA256:
        return _failed("source_hash_mismatch",
                       {"observed_sha256": observed_sha256, "expected_sha256": EXPECTED_SHA256})

    return {
        "status": "ok",
        "source": SOURCE,
        "doi": DOI,
        "license": LICENSE,
        "snapshot_sha256": observed_sha256,
        "row_count": len(rows),
        "feature_columns": list(EXPECTED_FEATURE_COLUMNS),
        "class_column": EXPECTED_CLASS_COLUMN,
        "class_counts": class_counts,
        "missing_values": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "check_script": os.path.relpath(__file__),
    }


def _failed(reason: str, detail: dict[str, object]) -> dict[str, object]:
    return {
        "status": "failed",
        "reason_code": reason,
        "source": SOURCE,
        "detail": detail,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_iris_input.py <path-to-data.csv>", file=sys.stderr)
        return 2
    record = check(Path(sys.argv[1]))
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
