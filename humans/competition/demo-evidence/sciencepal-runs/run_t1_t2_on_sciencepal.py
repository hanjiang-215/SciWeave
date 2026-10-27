#!/usr/bin/env python3
"""SciencePal 实际承担 T1/T2 的正式执行脚本（ai4-aaff 硬门槛交付物）。

用途：把 UCI Iris 的 T1 输入检查（check_iris_input.py）与 T2 基线分类
（run_iris_baseline.py）交给 SciencePal 沙箱真实执行，下载产物并落盘，
供评审核对「执行确实发生在 SciencePal，而非本机冒充」。

本脚本只做编排，不执行任何科研逻辑；科研逻辑全在 SciencePal 沙箱内完成。
不打印、不落盘 token；token 只从环境变量 / .env 读取。

用法（在 bridge 项目目录外也可以跑，路径用 --bridge 指定）：

    uv run python run_t1_t2_on_sciencepal.py --bridge <bridge目录> --workdir <本目录>

退出码：
    0 = 两次 run 均 completed 且 T1/T2 产物已下载并核对
    1 = 配置/用法错误
    2 = run 超时
    3 = run 失败或产物核对不通过
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

# 锁定的快照哈希（与证据卡一致，来自 ai4-483l / ai4-j7g2）
EXPECTED_SHA256 = "ea110d42c2240c77fd292751dfdc4db00c699fee569528ed33ca270838b6f9f4"
IRIS_CSV = "iris_data.csv"
CHECK_SCRIPT = "check_iris_input.py"
BASELINE_SCRIPT = "run_iris_baseline.py"

# 产物核对：T1 应输出 status:ok + 快照哈希；T2 应输出准确率与混淆矩阵
T1_EXPECTED_KEYS = {"status", "snapshot_sha256"}
T2_EXPECTED_KEYS = {"status", "method", "accuracy"}


def sha256_of(path: Path) -> str:
    """与证据卡一致：行尾归一化后计算，屏蔽 Git 的 LF/CRLF 检出差异。"""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def parse_json_from_text(text: str) -> dict | None:
    """从 SciencePal 产物文本中取出第一个 JSON 对象（脚本输出为单块 JSON）。"""
    start = text.find("{")
    if start == -1:
        return None
    # 逐层配平大括号，取出完整对象
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="SciencePal T1/T2 正式执行")
    parser.add_argument("--bridge", required=True,
                        help="sciencepal-bridge 项目目录（含 pyproject.toml 与 .env）")
    parser.add_argument("--workdir", default=".",
                        help="放置/读取 iris_data.csv 与脚本的工作目录（默认当前目录）")
    parser.add_argument("--timeout", type=float, default=600.0,
                        help="每次 run 的最长等待秒数（默认 600）")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="轮询间隔秒数（默认 5）")
    args = parser.parse_args()

    bridge = Path(args.bridge).resolve()
    workdir = Path(args.workdir).resolve()
    if not (bridge / "pyproject.toml").exists():
        print("错误：--bridge 不是 sciencepal-bridge 项目目录（缺 pyproject.toml）", file=sys.stderr)
        return 1
    for name in (IRIS_CSV, CHECK_SCRIPT, BASELINE_SCRIPT):
        if not (workdir / name).exists():
            print(f"错误：工作目录缺 {name}（应位于 {workdir}）", file=sys.stderr)
            return 1

    # 前置核对：输入快照与证据卡一致，避免把非锁定数据送给 SciencePal
    observed = sha256_of(workdir / IRIS_CSV)
    if observed != EXPECTED_SHA256:
        print(f"错误：iris_data.csv 哈希 {observed} != 锁定值 {EXPECTED_SHA256}", file=sys.stderr)
        return 1

    # ---- 加载 bridge 的 .env（只读键值；绝不打印 token 值）----
    dotenv = bridge / ".env"
    if dotenv.exists():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    else:
        print("警告：bridge 目录下没有 .env，将依赖已存在的环境变量", file=sys.stderr)

    # 包在 src 布局下；依赖由调用方以 `uv run`（bridge 项目）提供
    sys.path.insert(0, str(bridge / "src"))
    try:
        from sciencepal_bridge.config import BridgeConfig, ConfigError
        from sciencepal_bridge.client import HttpSciencePalClient, SciencePalError
        from sciencepal_bridge.service import SciencePalService
    except ImportError as exc:
        print(f"错误：无法导入 sciencepal_bridge（{exc}）。请在 --bridge 目录运行 uv sync 后用 uv run 启动本脚本", file=sys.stderr)
        return 1

    try:
        config = BridgeConfig.from_env()
        config.require_token()
    except (ConfigError, SciencePalError) as error:
        code = getattr(error, "code", "sciencepal_config_error")
        print(json.dumps({"error": {"code": code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 1

    client = HttpSciencePalClient(
        base_url=config.base_url,
        access_token=config.access_token,
        timeout=config.request_timeout_s,
    )
    service = SciencePalService(config, client=client)

    # ---- 输入文件必须落在 SCIENCEPAL_WORKSPACE 内（resolve_input 强约束）----
    # 复制一份到 workspace 的 `inputs/` 子目录，避免污染原工作目录。
    workspace = config.workspace
    inputs_dir = workspace / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[str, Path] = {}
    for name in (IRIS_CSV, CHECK_SCRIPT, BASELINE_SCRIPT):
        staged[name] = shutil.copy2(workdir / name, inputs_dir / name)

    epoch = int(time.time())
    outcomes = {"t1": None, "t2": None}

    # ---- T1：SciencePal 执行输入检查 ----
    t1_instruction = (
        "在沙箱中执行 python3 check_iris_input.py iris_data.csv，"
        "把它的完整标准输出原样保存为 /outputs/t1_check_result.json。"
        "不要改写、不要总结，只要执行结果本身。"
    )
    t1_files = [
        {"name": CHECK_SCRIPT, "path": str(staged[CHECK_SCRIPT])},
        {"name": IRIS_CSV, "path": str(staged[IRIS_CSV])},
    ]

    # ---- T2：SciencePal 执行基线分类 ----
    t2_instruction = (
        "在沙箱中执行 python3 run_iris_baseline.py iris_data.csv，"
        "把它的完整标准输出原样保存为 /outputs/t2_baseline_result.json。"
        "不要改写、不要总结，只要执行结果本身。"
    )
    t2_files = [
        {"name": BASELINE_SCRIPT, "path": str(staged[BASELINE_SCRIPT])},
        {"name": IRIS_CSV, "path": str(staged[IRIS_CSV])},
    ]

    for label, instruction, files in (
        ("t1", t1_instruction, t1_files),
        ("t2", t2_instruction, t2_files),
    ):
        print(f"--- {label}: 发起 run ---", flush=True)
        try:
            started = service.start(
                instruction=instruction,
                idempotency_key=f"iris-{label}:{epoch}",
                files=files,
            )
        except SciencePalError as error:
            print(json.dumps({"error": {"code": error.code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
            return 1
        run_id = started["run_id"]
        print(f"{label} run_id={run_id} queued", flush=True)

        deadline = time.monotonic() + args.timeout
        final_status = None
        while time.monotonic() < deadline:
            state = service.status(run_id)
            print(f"{label} status={state.get('status')}", flush=True)
            if state.get("terminal"):
                final_status = state
                break
            time.sleep(args.interval)
        else:
            print(f"错误：{label} run {run_id} 超时（>{args.timeout}s）", file=sys.stderr)
            return 2

        if final_status.get("status") != "completed":
            print(json.dumps({"error": {"stage": label, "run_id": run_id,
                                        "status": final_status.get("status"),
                                        "detail": final_status.get("error")}}, ensure_ascii=False), file=sys.stderr)
            return 3

        # 下载产物（sciencepal_collect 语义：收 /outputs 与 /workspace/outputs）
        collected = service.collect(run_id)
        outcomes[label] = {"run_id": run_id, "collected": collected}
        print(f"{label} completed，产物清单见 outcomes", flush=True)

    # ---- 核对 ----
    problems: list[str] = []
    for label, expected_keys, filename in (
        ("t1", T1_EXPECTED_KEYS, "t1_check_result.json"),
        ("t2", T2_EXPECTED_KEYS, "t2_baseline_result.json"),
    ):
        outcome = outcomes[label]
        artifacts = outcome["collected"].get("artifacts", [])
        matches = [a for a in artifacts if a.get("name") == filename]
        if not matches:
            problems.append(f"{label}: 未找到产物 {filename}（清单：{[a.get('name') for a in artifacts]}）")
            continue
        # collect() 的返回只有 name/path/sha256 元数据，产物内容落盘在
        # manifest_path 所在目录（workspace/runs/<run_id>/<relative>）。
        stated_path = matches[0].get("path")
        content = None
        manifest_path = outcome["collected"].get("manifest_path")
        if manifest_path and stated_path:
            artifact_file = Path(manifest_path).parent / Path(stated_path)
            if artifact_file.is_file():
                content = artifact_file.read_text(encoding="utf-8", errors="replace")
        if content is None:
            problems.append(f"{label}: 产物 {filename} 无法从落盘位置读取（path={stated_path}）")
            continue
        parsed = parse_json_from_text(content)
        if parsed is None:
            problems.append(f"{label}: 产物 {filename} 不是 JSON")
            continue
        missing = expected_keys - set(parsed.keys())
        if missing:
            problems.append(f"{label}: 产物缺少键 {sorted(missing)}")
        if label == "t1" and parsed.get("status") != "ok":
            problems.append(f"t1: status={parsed.get('status')}，应为 ok")

    if problems:
        print(json.dumps({"error": "artifact_check_failed", "problems": problems}, ensure_ascii=False), file=sys.stderr)
        return 3

    # ---- 落盘证据 ----
    manifest = {
        "tool": "run_t1_t2_on_sciencepal.py",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_snapshot_sha256": observed,
        "t1": outcomes["t1"],
        "t2": outcomes["t2"],
    }
    out = workdir / "sciencepal_t1_t2_evidence.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：证据写入 {out}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
