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
SNAPSHOT_SHA256 = "daaeb5e3e889d07fbdd44544f5a39fe2372a07172e25899d577be0ad74df9e65"


def load(path: Path) -> tuple[list[tuple[float, ...]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_iris_baseline.py <path-to-data.csv>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    features, labels = load(path)
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
        "input_snapshot_sha256": SNAPSHOT_SHA256,
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