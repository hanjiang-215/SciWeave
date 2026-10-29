import asyncio
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from audit_trail import query_audit_calls
from registry.config import RegistryConfig, TokenIdentity
from registry.server import create_registry_server


TOKENS = {
    "owner": TokenIdentity("person:owner", "project_owner"),
    "researcher": TokenIdentity("person:researcher", "researcher", "person:researcher"),
    "centre": TokenIdentity("service:centre", "service", service_role="centre"),
    "email": TokenIdentity("service:email", "service", service_role="email"),
}


class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        return


@pytest.fixture
def registry_mcp(tmp_path: Path):
    registry_path = tmp_path / "registry.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    map_path = tmp_path / "formal-map.sqlite"
    map_db = sqlite3.connect(map_path)
    map_db.execute("CREATE TABLE executor_refs (task_id TEXT PRIMARY KEY)")
    map_db.execute("INSERT INTO executor_refs (task_id) VALUES ('task:keep')")
    map_db.commit()
    map_db.close()
    config = RegistryConfig(
        host="127.0.0.1",
        port=0,
        sqlite_path=str(registry_path),
        audit_sqlite_path=str(audit_path),
        issuer_url="http://127.0.0.1/issuer",
        resource_url="http://127.0.0.1/registry",
        token_identities=TOKENS,
    )
    app = create_registry_server(config).streamable_http_app()
    server = _Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("registry server did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield {
            "mcp_url": f"http://127.0.0.1:{port}/mcp",
            "health_url": f"http://127.0.0.1:{port}/health",
            "registry_path": registry_path,
            "audit_path": audit_path,
            "map_path": map_path,
        }
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _session_call(mcp: dict, token: str, fn):
    async def run():
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(headers=headers, timeout=30) as http:
            async with streamable_http_client(mcp["mcp_url"], http_client=http) as (read, write, _session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)

    return asyncio.run(run())


def list_tools(mcp: dict, token: str):
    return _session_call(mcp, token, lambda session: session.list_tools())


def call_tool(mcp: dict, token: str, name: str, arguments: dict | None = None):
    return _session_call(mcp, token, lambda session: session.call_tool(name, arguments or {}))


def body(result) -> dict:
    assert result.isError is False
    assert result.structuredContent is not None
    return result.structuredContent


def error_code(result) -> str:
    assert result.isError is True
    return result.content[0].text.rsplit(": ", 1)[-1]


def formal_map_tasks(mcp: dict) -> list[str]:
    connection = sqlite3.connect(mcp["map_path"])
    try:
        return [row[0] for row in connection.execute("SELECT task_id FROM executor_refs ORDER BY task_id")]
    finally:
        connection.close()


def test_authenticated_caller_sees_registry_tools(registry_mcp):
    listed = list_tools(registry_mcp, "owner")
    assert {tool.name for tool in listed.tools} == {
        "register_principal",
        "register_workflow_agent",
        "register_agent_instance",
        "get_principal_contact",
        "get_agent_registration",
        "health",
    }


def test_missing_token_is_rejected_and_health_probe_stays_public(registry_mcp):
    unauthenticated = httpx.post(
        registry_mcp["mcp_url"],
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert unauthenticated.status_code == 401
    probe = httpx.get(registry_mcp["health_url"])
    assert probe.status_code == 200
    assert probe.json() == {"status": "ready", "service": "registry", "storage": "ready"}


def test_email_service_reads_current_contact_and_stable_contact_errors(registry_mcp):
    created = call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:a",
            "role": "researcher",
            "contact_email": "a@example.test",
            "idempotency_key": "p1",
        },
    )
    assert body(created)["duplicate"] is False
    contact = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
    assert body(contact) == {
        "principal_id": "person:a",
        "contact_email": "a@example.test",
        "status": "active",
        "contact_version": "contact:person:a:1",
    }

    missing = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:missing"})
    assert error_code(missing) == "principal_not_found"

    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {"principal_id": "person:b", "role": "researcher", "idempotency_key": "p2"},
    )
    no_email = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:b"})
    assert error_code(no_email) == "contact_missing"

    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:a",
            "role": "researcher",
            "contact_email": "a@example.test",
            "status": "disabled",
            "idempotency_key": "p3",
        },
    )
    disabled = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
    assert error_code(disabled) == "contact_disabled"

    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:a",
            "role": "researcher",
            "contact_email": "a@example.test",
            "status": "active",
            "idempotency_key": "p4",
        },
    )
    restored = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
    assert body(restored)["contact_email"] == "a@example.test"
    assert body(restored)["contact_version"] == "contact:person:a:3"
    assert formal_map_tasks(registry_mcp) == ["task:keep"]


def test_researcher_registers_only_their_own_endpoint_agent(registry_mcp):
    denied_principal = call_tool(
        registry_mcp,
        "researcher",
        "register_principal",
        {"principal_id": "person:other", "role": "researcher", "idempotency_key": "no-principal"},
    )
    assert error_code(denied_principal) == "denied"
    denied_centre = call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:centre",
            "workflow_id": "wf:centre",
            "kind": "centre",
            "workflow_kind": "review",
            "idempotency_key": "no-centre",
        },
    )
    assert error_code(denied_centre) == "denied"
    denied_other = call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:other",
            "workflow_id": "wf:other",
            "kind": "endpoint",
            "principal_id": "person:other",
            "workflow_kind": "task",
            "idempotency_key": "no-other",
        },
    )
    assert error_code(denied_other) == "denied"
    registered = call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "idempotency_key": "yes-self",
        },
    )
    assert body(registered)["agent_id"] == "agent:self"
    hidden = call_tool(registry_mcp, "researcher", "get_agent_registration", {"agent_id": "agent:self"})
    assert error_code(hidden) == "denied"


def test_centre_and_email_keep_separate_read_surfaces(registry_mcp):
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:researcher",
            "role": "researcher",
            "contact_email": "researcher@example.test",
            "idempotency_key": "principal",
        },
    )
    call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:endpoint",
            "workflow_id": "wf:endpoint",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "idempotency_key": "agent",
        },
    )

    contact = call_tool(
        registry_mcp, "email", "get_principal_contact", {"principal_id": "person:researcher"}
    )
    assert body(contact)["contact_email"] == "researcher@example.test"
    assert error_code(call_tool(
        registry_mcp, "email", "get_agent_registration", {"agent_id": "agent:endpoint"}
    )) == "denied"
    assert error_code(call_tool(
        registry_mcp,
        "email",
        "register_agent_instance",
        {"agent_id": "agent:endpoint", "agent_instance_id": "i1", "idempotency_key": "email-write"},
    )) == "denied"

    registration = call_tool(registry_mcp, "centre", "get_agent_registration", {"agent_id": "agent:endpoint"})
    assert body(registration)["agent"]["agent_id"] == "agent:endpoint"
    assert "executor_refs" not in body(registration)["agent"]
    assert error_code(call_tool(
        registry_mcp, "centre", "get_principal_contact", {"principal_id": "person:researcher"}
    )) == "denied"
    assert error_code(call_tool(
        registry_mcp,
        "centre",
        "register_workflow_agent",
        {
            "agent_id": "agent:other",
            "workflow_id": "wf:other",
            "kind": "centre",
            "workflow_kind": "review",
            "idempotency_key": "centre-write",
        },
    )) == "denied"


def test_status_changes_keep_history_and_multiple_instances(registry_mcp):
    call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "idempotency_key": "agent",
        },
    )
    for instance_id, status, key in (
        ("i1", "starting", "i1-start"),
        ("i1", "online", "i1-online"),
        ("i1", "offline", "i1-offline"),
        ("i1", "revoked", "i1-revoked"),
        ("i2", "starting", "i2-start"),
    ):
        call_tool(
            registry_mcp,
            "researcher",
            "register_agent_instance",
            {
                "agent_id": "agent:self",
                "agent_instance_id": instance_id,
                "runtime_status": status,
                "idempotency_key": key,
            },
        )
    call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "status": "retired",
            "idempotency_key": "retire",
        },
    )
    retired = body(call_tool(registry_mcp, "centre", "get_agent_registration", {"agent_id": "agent:self"}))
    assert retired["agent"]["status"] == "retired"
    assert {row["agent_instance_id"] for row in retired["instances"]} == {"i1", "i2"}
    assert retired["status_history"] == ["active", "retired"]
    assert retired["instance_status_history"]["i1"] == ["starting", "online", "offline", "revoked"]

    call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "status": "active",
            "idempotency_key": "restore",
        },
    )
    restored = body(call_tool(registry_mcp, "centre", "get_agent_registration", {"agent_id": "agent:self"}))
    assert restored["agent"]["status"] == "active"
    assert restored["status_history"] == ["active", "retired", "active"]
    assert formal_map_tasks(registry_mcp) == ["task:keep"]


def test_same_idempotency_key_replays_or_conflicts(registry_mcp):
    call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "idempotency_key": "agent",
        },
    )
    first = call_tool(
        registry_mcp,
        "researcher",
        "register_agent_instance",
        {
            "agent_id": "agent:self",
            "agent_instance_id": "i1",
            "runtime_status": "online",
            "idempotency_key": "same",
        },
    )
    replay = call_tool(
        registry_mcp,
        "researcher",
        "register_agent_instance",
        {
            "agent_id": "agent:self",
            "agent_instance_id": "i1",
            "runtime_status": "online",
            "idempotency_key": "same",
        },
    )
    assert body(first)["duplicate"] is False
    assert body(replay)["duplicate"] is True
    assert body(replay)["runtime_status"] == "online"
    conflict = call_tool(
        registry_mcp,
        "researcher",
        "register_agent_instance",
        {
            "agent_id": "agent:self",
            "agent_instance_id": "i1",
            "runtime_status": "offline",
            "idempotency_key": "same",
        },
    )
    assert error_code(conflict) == "idempotency_conflict"
    registration = body(call_tool(registry_mcp, "centre", "get_agent_registration", {"agent_id": "agent:self"}))
    assert registration["instances"][0]["runtime_status"] == "online"


def test_identity_conflicts_leave_the_original_record(registry_mcp):
    call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "idempotency_key": "agent",
        },
    )
    call_tool(
        registry_mcp,
        "researcher",
        "register_agent_instance",
        {"agent_id": "agent:self", "agent_instance_id": "i1", "idempotency_key": "instance"},
    )
    stolen = call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:other",
            "workflow_kind": "task",
            "idempotency_key": "steal",
        },
    )
    assert error_code(stolen) == "agent_owner_conflict"
    call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:centre",
            "workflow_id": "wf:centre",
            "kind": "centre",
            "workflow_kind": "review",
            "idempotency_key": "centre-agent",
        },
    )
    moved = call_tool(
        registry_mcp,
        "owner",
        "register_agent_instance",
        {
            "agent_id": "agent:centre",
            "agent_instance_id": "i1",
            "runtime_status": "online",
            "idempotency_key": "move",
        },
    )
    assert error_code(moved) == "instance_identity_conflict"
    registration = body(call_tool(registry_mcp, "centre", "get_agent_registration", {"agent_id": "agent:self"}))
    assert registration["agent"]["principal_id"] == "person:researcher"
    assert registration["instances"][0]["agent_instance_id"] == "i1"


def test_audit_ledger_records_the_call_but_not_the_contact(registry_mcp):
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:researcher",
            "role": "researcher",
            "contact_email": "researcher@example.test",
            "idempotency_key": "principal",
        },
    )
    denied = call_tool(
        registry_mcp,
        "researcher",
        "register_principal",
        {"principal_id": "person:other", "role": "researcher", "idempotency_key": "denied"},
    )
    assert error_code(denied) == "denied"

    audit = sqlite3.connect(registry_mcp["audit_path"])
    audit.row_factory = sqlite3.Row
    try:
        calls = query_audit_calls(audit, service="registry", tool="register_principal")
    finally:
        audit.close()
    assert {row["result"] for row in calls} >= {"ok", "denied"}
    denied_row = next(row for row in calls if row["result"] == "denied")
    assert denied_row["error_code"] == "denied"
    assert denied_row["caller_id"] == "person:researcher"
    assert denied_row["channel_id"] == "mcp-streamable-http"
    for row in calls:
        for value in tuple(row):
            if isinstance(value, str):
                assert "researcher@example.test" not in value


def test_failed_audit_blocks_writes_and_still_allows_contact_reads(registry_mcp):
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:a",
            "role": "researcher",
            "contact_email": "a@example.test",
            "idempotency_key": "kept",
        },
    )
    locker = sqlite3.connect(registry_mcp["audit_path"])
    locker.execute("BEGIN EXCLUSIVE")
    try:
        blocked = call_tool(
            registry_mcp,
            "owner",
            "register_principal",
            {"principal_id": "person:b", "role": "researcher", "idempotency_key": "blocked"},
        )
        assert error_code(blocked) == "audit_unavailable"
        contact = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
        assert body(contact)["contact_email"] == "a@example.test"
    finally:
        locker.rollback()
        locker.close()
    missing = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:b"})
    assert error_code(missing) == "principal_not_found"


def test_storage_failure_reports_unavailable_without_changing_the_formal_map(registry_mcp):
    registry_mcp["registry_path"].write_bytes(b"not a database")
    probe = httpx.get(registry_mcp["health_url"])
    assert probe.status_code == 503
    assert probe.json() == {"status": "unavailable", "service": "registry", "storage": "unavailable"}
    failed = call_tool(registry_mcp, "centre", "health")
    assert error_code(failed) == "registry_unavailable"
    contact = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
    assert error_code(contact) == "registry_unavailable"
    assert formal_map_tasks(registry_mcp) == ["task:keep"]


def test_status_update_keeps_omitted_contact_and_last_seen(registry_mcp):
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:a",
            "role": "researcher",
            "contact_email": "a@example.test",
            "idempotency_key": "create",
        },
    )
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {"principal_id": "person:a", "role": "researcher", "status": "disabled", "idempotency_key": "disable"},
    )
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {"principal_id": "person:a", "role": "researcher", "status": "active", "idempotency_key": "restore"},
    )
    restored = call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
    assert body(restored)["contact_email"] == "a@example.test"

    call_tool(
        registry_mcp,
        "researcher",
        "register_workflow_agent",
        {
            "agent_id": "agent:self",
            "workflow_id": "wf:self",
            "kind": "endpoint",
            "principal_id": "person:researcher",
            "workflow_kind": "task",
            "idempotency_key": "agent",
        },
    )
    call_tool(
        registry_mcp,
        "researcher",
        "register_agent_instance",
        {
            "agent_id": "agent:self",
            "agent_instance_id": "i1",
            "runtime_status": "online",
            "last_seen_at": "2026-10-24T00:00:00Z",
            "idempotency_key": "seen",
        },
    )
    call_tool(
        registry_mcp,
        "researcher",
        "register_agent_instance",
        {
            "agent_id": "agent:self",
            "agent_instance_id": "i1",
            "runtime_status": "offline",
            "idempotency_key": "offline",
        },
    )
    registration = body(call_tool(registry_mcp, "centre", "get_agent_registration", {"agent_id": "agent:self"}))
    assert registration["instances"][0]["last_seen_at"] == "2026-10-24T00:00:00Z"
    assert "deployment_description" not in registration["agent"]


def test_successful_read_is_recorded_in_the_audit_ledger(registry_mcp):
    call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {
            "principal_id": "person:a",
            "role": "researcher",
            "contact_email": "a@example.test",
            "idempotency_key": "create",
        },
    )
    call_tool(registry_mcp, "email", "get_principal_contact", {"principal_id": "person:a"})
    audit = sqlite3.connect(registry_mcp["audit_path"])
    audit.row_factory = sqlite3.Row
    try:
        calls = query_audit_calls(audit, service="registry", tool="get_principal_contact")
    finally:
        audit.close()
    assert len(calls) == 1
    assert calls[0]["phase"] == "attempted"
    assert calls[0]["caller_id"] == "service:email"
    assert "a@example.test" not in " ".join(str(value) for value in tuple(calls[0]) if value is not None)


def test_audit_storage_failure_makes_both_health_checks_unavailable(registry_mcp):
    # Drop the ledger table through a second connection to the same file instead
    # of overwriting the database bytes: the WAL -shm sidecar is held open by the
    # running server and cannot be overwritten on Windows, while a schema drop is
    # visible to the server's held connection on the next query (no such table).
    vandal = sqlite3.connect(registry_mcp["audit_path"])
    try:
        vandal.execute("DROP TABLE audit_call")
        vandal.commit()
    finally:
        vandal.close()
    probe = httpx.get(registry_mcp["health_url"])
    assert probe.status_code == 503
    assert probe.json() == {"status": "unavailable", "service": "registry", "storage": "unavailable"}
    failed = call_tool(registry_mcp, "centre", "health")
    assert error_code(failed) == "registry_unavailable"
    assert formal_map_tasks(registry_mcp) == ["task:keep"]


def test_register_principal_accepts_service_role(registry_mcp):
    # B10: a service principal can be registered directly, matching the
    # service:xxx principal ids register_workflow_agent already accepts.
    result = call_tool(
        registry_mcp,
        "owner",
        "register_principal",
        {"principal_id": "service:bridge", "role": "service", "idempotency_key": "svc-1"},
    )
    assert "error" not in body(result)
    assert body(result)["principal_id"] == "service:bridge"
    assert body(result)["status"] == "active"


def test_register_workflow_agent_endpoint_requires_principal(registry_mcp):
    # B11: for kind=endpoint a missing principal_id must fail principal_required,
    # while the schema stays optional so kind=centre (empty) still works.
    missing = call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:no-principal",
            "workflow_id": "wf:x",
            "kind": "endpoint",
            "workflow_kind": "review",
            "idempotency_key": "endpoint-no-principal",
        },
    )
    assert error_code(missing) == "principal_required"

    centre = call_tool(
        registry_mcp,
        "owner",
        "register_workflow_agent",
        {
            "agent_id": "agent:centre-ok",
            "workflow_id": "wf:centre",
            "kind": "centre",
            "workflow_kind": "review",
            "idempotency_key": "centre-ok",
        },
    )
    assert "error" not in body(centre)
    assert body(centre)["agent_id"] == "agent:centre-ok"


def test_an_unexpected_operation_error_does_not_leave_a_transaction_open() -> None:
    """ai4-onvr: a non-RegistryError from operation() used to keep BEGIN open."""
    import sqlite3

    from registry.service import RegistryService

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    service = RegistryService(conn)

    def explode() -> dict:
        conn.execute(
            "INSERT INTO operation(operation_id, idempotency_key, caller_id, action, target_id,"
            " request_json, result_json) VALUES(?,?,?,?,?,?,?)",
            ("o-tmp", "k-tmp", "c", "probe", "t", "{}", "{}"),
        )
        raise RuntimeError("boom")

    caller = type("Caller", (), {"caller_id": "c", "caller_type": "researcher"})()
    payload = {"idempotency_key": "k-tmp"}
    with pytest.raises(RuntimeError):
        service._write(caller, payload, "probe", "t", explode)

    assert conn.in_transaction is False
    # The rolled-back row is gone and the connection still accepts writes.
    assert conn.execute("SELECT COUNT(*) FROM operation").fetchone()[0] == 0
    service._write(caller, {"idempotency_key": "k-ok"}, "probe", "t", lambda: {"ok": True})
    assert conn.execute("SELECT COUNT(*) FROM operation").fetchone()[0] == 1
