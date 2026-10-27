"""Seed a persistent Research Mapping domain so the Web dashboard shows real data.

The dashboard reads a formal mapping revision through the research-map
``FormalQueryService``. Without a seeded domain that service answers
``unavailable`` and the browser falls back to a fixture snapshot, so this
script creates the minimal real state a dashboard needs:

1. a TerminusDB database with the ``TaskNode`` / ``DependencyEdge`` schema,
2. the formal ``T1 -> T2 -> T3`` route as immutable graph content,
3. the matching formal revision in a persistent SQLite store, pointed at the
   exact TerminusDB commit that holds that content.

The script is idempotent: when the database already exists and SQLite already
records a current formal revision it exits without touching either store.
``--reset`` drops the TerminusDB database and rebuilds both sides.

Only the Python standard library and this repository's research-map sources are
used; every connection setting comes from the environment. Nothing here belongs
to the competition evidence package (``humans/competition/demo-evidence``) —
that package must stay a self-contained, temp-database run.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_MAP_SRC = ROOT / "sci-weave" / "centre-control" / "research-map" / "src"
if str(RESEARCH_MAP_SRC) not in sys.path:
    sys.path.insert(0, str(RESEARCH_MAP_SRC))

from research_mapping.domain import (  # noqa: E402
    FormalMappingRevision,
    FormalizationResult,
)
from research_mapping.sqlite_store import SqliteStore  # noqa: E402

DEFAULT_DOMAIN = "iris-demo"
DEFAULT_DATABASE = "sciweave_dashboard_demo"
DEFAULT_COMMIT_TIME = "2026-10-24T00:00:00Z"

SCHEMA = [
    {
        "@type": "Class",
        "@id": "TaskNode",
        "@key": {"@type": "Lexical", "@fields": ["version_id"]},
        "mapping_domain_id": "xsd:string",
        "logical_id": "xsd:string",
        "version_id": "xsd:string",
        "title": "xsd:string",
        "objective": "xsd:string",
        "scope": "xsd:string",
        "acceptance_criteria": {"@type": "Set", "@class": "xsd:string"},
        "expected_outputs": {"@type": "Set", "@class": "xsd:string"},
        "required_evidence": {"@type": "Set", "@class": "xsd:string"},
        "task_owner_id": "xsd:string",
        "lifecycle_state": "xsd:string",
        "execution_status": {"@type": "Optional", "@class": "xsd:string"},
        "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
        "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
        "created_by": "xsd:string",
        "created_at": "xsd:string",
    },
    {
        "@type": "Class",
        "@id": "DependencyEdge",
        "@key": {"@type": "Lexical", "@fields": ["version_id"]},
        "mapping_domain_id": "xsd:string",
        "logical_id": "xsd:string",
        "version_id": "xsd:string",
        "source_node_version_ref": {"@type": "Optional", "@class": "xsd:string"},
        "target_node_version_ref": {"@type": "Optional", "@class": "xsd:string"},
        "dependency_kind": "xsd:string",
        "lifecycle_state": "xsd:string",
        "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
        "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
        "created_by": "xsd:string",
        "created_at": "xsd:string",
    },
]

ROUTE = (
    ("t1-v1", "T1 固定并检查输入", "succeeded"),
    ("t2-v1", "T2 执行基线分类", "succeeded"),
    ("t3-v1", "T3 研究人员复核并接纳", "waiting"),
)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


class _BasicAuth:
    def __init__(self, username: str, password: str) -> None:
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._header = f"Basic {token}"

    def at(self, url: str, *, method: str = "GET", payload: object = None) -> tuple[int, bytes]:
        body = None
        headers = {"Accept": "application/json", "Authorization": self._header}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()


def _task_node(version_id: str, title: str, domain: str, execution_status: str) -> dict:
    return {
        "@type": "TaskNode",
        "@id": f"TaskNode/{version_id}",
        "mapping_domain_id": domain,
        "logical_id": f"task-{version_id}",
        "version_id": version_id,
        "title": title,
        "objective": "Reproduce the UCI Iris baseline through the tracked route",
        "scope": "Dashboard seed",
        "acceptance_criteria": ["Input snapshot is fixed and checkable"],
        "expected_outputs": ["Formal route revision"],
        "required_evidence": ["Owner approval"],
        "task_owner_id": "project-owner",
        "lifecycle_state": "formal",
        "execution_status": execution_status,
        "created_by": "dashboard-seed",
        "created_at": DEFAULT_COMMIT_TIME,
    }


def _edge(edge_id: str, source: str, target: str, domain: str) -> dict:
    return {
        "@type": "DependencyEdge",
        "@id": f"DependencyEdge/{edge_id}",
        "mapping_domain_id": domain,
        "logical_id": f"edge-{edge_id}",
        "version_id": edge_id,
        "source_node_version_ref": source,
        "target_node_version_ref": target,
        "dependency_kind": "blocks",
        "lifecycle_state": "formal",
        "created_by": "dashboard-seed",
        "created_at": DEFAULT_COMMIT_TIME,
    }


def _current_formal_revision(sqlite: SqliteStore, domain: str) -> str | None:
    return sqlite.get_current_formal_revision_id(domain)


def seed(*, reset: bool) -> int:
    base_url = _env("SCIWEAVE_MAPPING_TERMINUSDB_URL", "http://127.0.0.1:6363").rstrip("/")
    store_id = _env("SCIWEAVE_MAPPING_TERMINUSDB_STORE", "admin")
    database = _env("SCIWEAVE_MAPPING_TERMINUSDB_DATABASE", DEFAULT_DATABASE)
    username = _env("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME")
    password = _env("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD")
    domain = _env("SCIWEAVE_MAPPING_DOMAIN_ID", DEFAULT_DOMAIN)
    sqlite_path = _env(
        "SCIWEAVE_MAPPING_SQLITE_PATH",
        str(ROOT / "sci-weave" / "centre-control" / "research-map" / "data" / "dashboard.sqlite"),
    )
    if not username or not password:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": "SCIWEAVE_MAPPING_TERMINUSDB_USERNAME and SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD are required",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    auth = _BasicAuth(username, password)
    database_url = f"{base_url}/api/db/{store_id}/{database}"

    sqlite = SqliteStore(sqlite_path)
    sqlite.initialize()
    existing = _current_formal_revision(sqlite, domain)
    if existing and not reset:
        print(
            json.dumps(
                {
                    "status": "already_seeded",
                    "mapping_domain_id": domain,
                    "terminusdb_database": database,
                    "sqlite_path": sqlite_path,
                    "formal_revision_id": existing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if reset:
        auth.at(database_url, method="DELETE")

    status, body = auth.at(database_url, method="POST", payload={"label": "SciWeave dashboard", "comment": "dashboard seed"})
    if status not in (200, 409):
        print(json.dumps({"status": "failed", "error": f"database creation failed ({status}): {body[:300]!r}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    status, body = auth.at(
        f"{base_url}/api/document/{store_id}/{database}?graph_type=schema&author=dashboard-seed&message=schema",
        method="POST",
        payload=SCHEMA,
    )
    if status != 200:
        print(json.dumps({"status": "failed", "error": f"schema setup failed ({status}): {body[:300]!r}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    documents = [_task_node(version_id, title, domain, status) for version_id, title, status in ROUTE]
    documents.append(_edge("t1-t2", "t1-v1", "t2-v1", domain))
    documents.append(_edge("t2-t3", "t2-v1", "t3-v1", domain))
    status, body = auth.at(
        f"{base_url}/api/document/{store_id}/{database}?author=dashboard-seed&message=seed-formal-route",
        method="POST",
        payload=documents,
    )
    if status != 200:
        print(json.dumps({"status": "failed", "error": f"route seed failed ({status}): {body[:300]!r}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    status, body = auth.at(f"{base_url}/api/log/{store_id}/{database}/local/branch/main?count=1")
    if status != 200:
        print(json.dumps({"status": "failed", "error": f"commit lookup failed ({status}): {body[:300]!r}"}, ensure_ascii=False), file=sys.stderr)
        return 1
    commit_hash = json.loads(body.decode())[0]["identifier"]
    revision_id = f"rev-dashboard-{commit_hash[:12]}"

    sqlite.add_formal_revision(
        FormalMappingRevision(
            formal_revision_id=revision_id,
            mapping_domain_id=domain,
            terminus_store_id=store_id,
            formal_branch_id="main",
            formal_commit_hash=commit_hash,
            base_formal_revision_id=None,
            source_proposal_id=None,
            approval_audit_event_id=None,
            published_by="project-owner",
            published_at=DEFAULT_COMMIT_TIME,
        )
    )
    sqlite.add_formalization_result(
        FormalizationResult(
            result_id=f"seed-result-{commit_hash[:12]}",
            mapping_domain_id=domain,
            formalization_operation_id=f"seed-operation-{commit_hash[:12]}",
            attempt_number=1,
            result_status="succeeded",
            formal_revision_id=revision_id,
            terminus_store_id=store_id,
            formal_commit_hash=commit_hash,
            recorded_at=DEFAULT_COMMIT_TIME,
        )
    )
    sqlite.set_current_formal_revision(domain, revision_id, updated_at=DEFAULT_COMMIT_TIME)

    print(
        json.dumps(
            {
                "status": "seeded",
                "mapping_domain_id": domain,
                "terminusdb_database": database,
                "terminusdb_commit": commit_hash,
                "sqlite_path": sqlite_path,
                "formal_revision_id": revision_id,
                "task_nodes": len(ROUTE),
                "dependency_edges": 2,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop and rebuild the dashboard seed")
    args = parser.parse_args()
    return seed(reset=args.reset)


if __name__ == "__main__":
    raise SystemExit(main())
