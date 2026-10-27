#!/usr/bin/env python3
"""T2 执行基线分类：固定参数的确定性 KNN 分类模板。

只使用 Python 标准库。这是 `ai4-aaff` 中 T2 任务的确定性执行模板：
- 固定随机种子与参数，输出可复现的准确率、混淆矩阵与分隔信息；
- 分层划分为训练/测试集，保证三类都在划分里；
- 输出 JSON 证据，供 SciencePal 封装实际运行时直接参照或替换。

此脚本本人可运行，证明演示闭环在平台外可复现；SciencePal 实际
承接执行并回填工具/版本仍是赛事硬门槛，本脚本不替代该证据。
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SEED = 20261023
K = 3
TEST_RATIO = 0.3
FEATURE_COLUMNS = ("sepal length", "sepal width", "petal length", "petal width")
CLASS_COLUMN = "class"
SNAPSHOT_SHA256 = "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4"


def sha256_of(path: Path) -> str:
    """Hash the snapshot content, not the working copy's line endings.

    Same normalisation as ``check_iris_input.py`` so the two scripts agree on
    what the pinned snapshot is (``ai4-483l``, ``ai4-j7g2``).
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load(path: Path) -> tuple[list[tuple[float, ...]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = [column for column in (*FEATURE_COLUMNS, CLASS_COLUMN) if column not in columns]
        if missing:
            raise MissingColumnsError(missing, columns)
        features: list[tuple[float, ...]] = []
        labels: list[str] = []
        for row in reader:
            values = tuple(float(row[column]) for column in FEATURE_COLUMNS)
            features.append(values)
            labels.append(row[CLASS_COLUMN])
    return features, labels


def stratified_split(features: list[tuple[float, ...]], labels: list[str], rng) -> tuple[list, list, list, list]:
    indices_by_label: dict[str, list[int]] = {}
    for index, label in enumerate(labels):
        indices_by_label.setdefault(label, []).append(index)
    train, test = [], []
    for label, indices in indices_by_label.items():
        rng.shuffle(indices)
        split = max(1, round(len(indices) * (1 - TEST_RATIO)))
        train.extend(indices[:split])
        test.extend(indices[split:])
    rng.shuffle(train)
    rng.shuffle(test)
    return ([features[i] for i in train], [labels[i] for i in train],
            [features[i] for i in test], [labels[i] for i in test])


def predict_one(trained: list[tuple[tuple[float, ...], str]], point: tuple[float, ...], k: int) -> str:
    distances = []
    for vector, label in trained:
        distances.append((_euclidean(vector, point), label))
    distances.sort(key=lambda item: item[0])
    neighbours = Counter(label for _, label in distances[:k])
    return neighbours.most_common(1)[0][0]


def _euclidean(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


class MissingColumnsError(ValueError):
    """输入缺少必需列；属于结构错误，不进入分类计算。"""

    def __init__(self, missing: list[str], columns: list[str]) -> None:
        super().__init__(f"missing columns: {', '.join(missing)}")
        self.missing = missing
        self.columns = columns


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_iris_baseline.py <path-to-data.csv>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        features, labels = load(path)
    except MissingColumnsError as error:
        print(json.dumps({
            "status": "failed",
            "reason_code": "missing_columns",
            "detail": {"missing": error.missing, "columns": error.columns},
            "run_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2))
        return 1
    observed_sha256 = sha256_of(path)
    if observed_sha256 != SNAPSHOT_SHA256:
        print(json.dumps({
            "status": "failed",
            "reason_code": "source_hash_mismatch",
            "detail": {"observed_sha256": observed_sha256, "expected_sha256": SNAPSHOT_SHA256},
            "run_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2))
        return 1
    rng = __import__("random").Random(SEED)
    xtrain, ytrain, xtest, ytest = stratified_split(features, labels, rng)
    trained = list(zip(xtrain, ytrain))
    predictions = [predict_one(trained, point, K) for point in xtest]

    labels_sorted = sorted(set(labels))
    confusion = {row: {col: 0 for col in labels_sorted} for row in labels_sorted}
    for actual, predicted in zip(ytest, predictions):
        confusion[actual][predicted] += 1
    correct = sum(1 for actual, predicted in zip(ytest, predictions) if actual == predicted)

    record = {
        "status": "ok",
        "method": "knn",
        "k": K,
        "seed": SEED,
        "test_ratio": TEST_RATIO,
        "feature_columns": list(FEATURE_COLUMNS),
        "input_snapshot_sha256": observed_sha256,
        "train_size": len(ytrain),
        "test_size": len(ytest),
        "accuracy": round(correct / len(ytest), 6),
        "correct": correct,
        "confusion_matrix": confusion,
        "tool_versions": {"python": sys.version.split()[0], "libraries": "standard-library-only"},
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())