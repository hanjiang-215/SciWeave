"""两个演示脚本共用的测试夹具。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

EVIDENCE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT = EVIDENCE_DIR / "iris_data.csv"
FAILURE_FIXTURE = EVIDENCE_DIR / "iris_data_failure_inject.csv"

# 快照哈希以字面量出现于五个地方，任何一处单独漂移都无法被代码发现。
# check_iris_input.py、run_iris_baseline.py、README.md、evidence-card.md、
# sciencpal-onboarding/agent/t2-baseline-agent.md 必须同时更新。
PINNED_SHA256 = "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4"

# 旧值：在 CRLF 工作副本上算出的哈希，行尾未归一化。任何文件再出现它都是回归。
STALE_SHA256 = "daaeb5e3e889d07fbdd44544f5a39fe2372a07172e25899d577be0ad74df9e65"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
