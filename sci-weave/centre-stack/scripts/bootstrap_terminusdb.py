"""为中央服务准备 TerminusDB 数据库。

三个领域各自要求数据库**已存在**：research-map 与 research-wiki 在读到 404 时
不会自行建库，草稿箱在初始化 schema 时拿到 404 直接退出（`schema_initialization_failed`）。
本地演示链路靠播种脚本建库，单容器部署缺了这一步，于是 buffer 一直 FATAL、
看板的 mapping / wiki 来源一直是 `unavailable`。

这个脚本按服务自己读的那套环境变量建库，幂等：已存在就跳过。用法——

    docker compose --env-file .env run --rm bootstrap

只有标准库；不做 schema 初始化（各服务启动时自己写 schema）。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request

# (标签, URL 变量, 数据库变量, store 变量, 用户名变量, 密码变量)
_TARGETS = (
    (
        "mapping",
        "SCIWEAVE_MAPPING_TERMINUSDB_URL",
        "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE",
        "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
        "SCIWEAVE_MAPPING_TERMINUSDB_USERNAME",
        "SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD",
    ),
    (
        "wiki",
        "SCIWEAVE_WIKI_TERMINUSDB_URL",
        "SCIWEAVE_WIKI_TERMINUSDB_DATABASE",
        "SCIWEAVE_WIKI_TERMINUSDB_STORE",
        "SCIWEAVE_WIKI_TERMINUSDB_USERNAME",
        "SCIWEAVE_WIKI_TERMINUSDB_PASSWORD",
    ),
    (
        "buffer",
        "SCIWEAVE_BUFFER_TERMINUSDB_URL",
        "SCIWEAVE_BUFFER_TERMINUSDB_DATABASE",
        "SCIWEAVE_BUFFER_TERMINUSDB_STORE",
        "SCIWEAVE_BUFFER_TERMINUSDB_USERNAME",
        "SCIWEAVE_BUFFER_TERMINUSDB_PASSWORD",
    ),
)


def _auth_header(username: str, password: str) -> dict[str, str]:
    if not username and not password:
        return {}
    raw = f"{username}:{password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}


def _request(
    url: str, *, method: str, headers: dict[str, str], body: bytes | None = None, timeout: float = 15.0
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _existing_databases(base_url: str, store: str, headers: dict[str, str]) -> set[str]:
    status, body = _request(f"{base_url}/api/db/{store}", method="GET", headers=headers)
    if status != 200:
        raise RuntimeError(f"cannot list databases of store {store!r}: HTTP {status} {body[:120]!r}")
    entries = json.loads(body.decode("utf-8") or "[]")
    names: set[str] = set()
    for entry in entries:
        path = str(entry.get("path", ""))
        if "/" in path:
            names.add(path.split("/", 1)[1])
    return names


def ensure_database(base_url: str, store: str, database: str, headers: dict[str, str]) -> str:
    existing = _existing_databases(base_url, store, headers)
    if database in existing:
        return "present"
    status, body = _request(
        f"{base_url}/api/db/{store}/{database}",
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
        # TerminusDB 12 要求 label 必填，缺了返回 400 api:MissingParameter。
        body=json.dumps({"label": database, "comment": "SciWeave central service"}).encode("utf-8"),
    )
    # TerminusDB 12.0.8 对已存在的库返回 400 + api:DatabaseAlreadyExists，不是 409。
    if status in (200, 201):
        return "created"
    if status == 400 and b"DatabaseAlreadyExists" in body:
        return "present"
    raise RuntimeError(f"cannot create database {store}/{database}: HTTP {status} {body[:200]!r}")


def main() -> int:
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for label, url_var, db_var, store_var, user_var, password_var in _TARGETS:
        base_url = (os.environ.get(url_var) or "").strip().rstrip("/")
        database = (os.environ.get(db_var) or "").strip()
        # buffer 没有 store 变量：它把 store 固定成 admin，所以缺省补 admin。
        store = (os.environ.get(store_var) or "").strip() or "admin"
        username = (os.environ.get(user_var) or "").strip()
        password = os.environ.get(password_var) or ""
        if not base_url or not database or not store:
            failures.append({"domain": label, "reason": f"{url_var} / {db_var} / {store_var} must be set"})
            continue
        try:
            outcome = ensure_database(base_url, store, database, _auth_header(username, password))
        except Exception as error:  # noqa: BLE001 - 引导脚本要把每个域的结果都报全
            failures.append({"domain": label, "database": f"{store}/{database}", "error": str(error)})
        else:
            results.append({"domain": label, "database": f"{store}/{database}", "outcome": outcome})
    payload = {"ready": not failures, "databases": results, "failures": failures}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())