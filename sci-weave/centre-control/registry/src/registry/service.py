from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Caller:
    caller_id: str
    caller_type: str


class RegistryError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class RegistryService:
    def __init__(self, connection: sqlite3.Connection, audit: Any = None) -> None:
        self.conn = connection
        self.conn.row_factory = sqlite3.Row
        self.audit = audit
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS principal (
          principal_id TEXT PRIMARY KEY, role TEXT NOT NULL,
          contact_email TEXT, status TEXT NOT NULL, contact_version INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS workflow_agent (
          agent_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, kind TEXT NOT NULL,
          principal_id TEXT, workflow_kind TEXT NOT NULL, created_by TEXT NOT NULL,
          status TEXT NOT NULL, deployment_description TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agent_instance (
          agent_id TEXT NOT NULL, agent_instance_id TEXT NOT NULL, runtime_status TEXT NOT NULL,
          last_seen_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (agent_id, agent_instance_id),
          FOREIGN KEY (agent_id) REFERENCES workflow_agent(agent_id)
        );
        CREATE TABLE IF NOT EXISTS operation (
          operation_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
          caller_id TEXT NOT NULL, action TEXT NOT NULL, target_id TEXT NOT NULL,
          request_json TEXT NOT NULL, result_json TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()

    def register_principal(self, caller: Caller, p: dict[str, Any]) -> dict[str, Any]:
        self._require(caller, {"project_owner"})
        pid = self._required(p, "principal_id")
        role = p.get("role")
        if role not in {"researcher", "project_owner"}:
            raise RegistryError("invalid_role")
        return self._write(caller, p, "register_principal", pid, lambda: self._upsert_principal(pid, role, p.get("contact_email"), p.get("status", "active")))

    def register_workflow_agent(self, caller: Caller, p: dict[str, Any]) -> dict[str, Any]:
        kind = p.get("kind")
        if kind == "endpoint":
            self._require_self_or_owner(caller, p.get("principal_id"))
            if not p.get("principal_id"):
                raise RegistryError("principal_required")
        elif kind == "centre":
            self._require(caller, {"project_owner"})
            if p.get("principal_id") is not None:
                raise RegistryError("centre_principal_must_be_empty")
        else:
            raise RegistryError("invalid_agent_kind")
        agent_id = self._required(p, "agent_id")
        return self._write(caller, p, "register_workflow_agent", agent_id, lambda: self._upsert_agent(p))

    def register_agent_instance(self, caller: Caller, p: dict[str, Any]) -> dict[str, Any]:
        agent_id = self._required(p, "agent_id")
        row = self.conn.execute("SELECT principal_id FROM workflow_agent WHERE agent_id=?", (agent_id,)).fetchone()
        if row is None:
            raise RegistryError("agent_not_found")
        self._require_self_or_owner(caller, row[0])
        instance_id = self._required(p, "agent_instance_id")
        return self._write(caller, p, "register_agent_instance", f"{agent_id}:{instance_id}", lambda: self._upsert_instance(p))

    def get_principal_contact(self, caller: Caller, p: dict[str, Any]) -> dict[str, Any]:
        self._require(caller, {"service", "project_owner"})
        pid = self._required(p, "principal_id")
        row = self.conn.execute("SELECT * FROM principal WHERE principal_id=?", (pid,)).fetchone()
        if row is None: raise RegistryError("principal_not_found")
        if row["status"] != "active": raise RegistryError("contact_disabled")
        if not row["contact_email"]: raise RegistryError("contact_missing")
        return {"principal_id": pid, "contact_email": row["contact_email"], "contact_version": f"contact:{pid}:{row['contact_version']}"}

    def get_agent_registration(self, caller: Caller, p: dict[str, Any]) -> dict[str, Any]:
        self._require(caller, {"service", "project_owner"})
        agent_id = self._required(p, "agent_id")
        agent = self.conn.execute("SELECT * FROM workflow_agent WHERE agent_id=?", (agent_id,)).fetchone()
        if agent is None: raise RegistryError("agent_not_found")
        instances = self.conn.execute("SELECT * FROM agent_instance WHERE agent_id=?", (agent_id,)).fetchall()
        return {"agent": dict(agent), "instances": [dict(x) for x in instances]}

    def health(self, caller: Caller) -> dict[str, str]:
        self._require(caller, {"service", "project_owner"})
        self.conn.execute("SELECT 1").fetchone()
        return {"status": "ready", "service": "registry", "api_version": "v1", "storage": "ready"}

    def _upsert_principal(self, pid: str, role: str, email: str | None, status: str) -> dict[str, Any]:
        self.conn.execute("""INSERT INTO principal(principal_id,role,contact_email,status)
          VALUES(?,?,?,?) ON CONFLICT(principal_id) DO UPDATE SET role=excluded.role,
          contact_email=excluded.contact_email,status=excluded.status,contact_version=principal.contact_version+1,
          updated_at=CURRENT_TIMESTAMP""", (pid, role, email, status)); self.conn.commit(); return {"principal_id": pid, "status": status}

    def _upsert_agent(self, p: dict[str, Any]) -> dict[str, Any]:
        self.conn.execute("""INSERT INTO workflow_agent(agent_id,workflow_id,kind,principal_id,workflow_kind,created_by,status,deployment_description)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET workflow_id=excluded.workflow_id,
          status=excluded.status,updated_at=CURRENT_TIMESTAMP""", (p["agent_id"],p["workflow_id"],p["kind"],p.get("principal_id"),p["workflow_kind"],p.get("created_by", ""),p.get("status", "active"),p.get("deployment_description"))); self.conn.commit(); return {"agent_id": p["agent_id"], "status": p.get("status", "active")}

    def _upsert_instance(self, p: dict[str, Any]) -> dict[str, Any]:
        self.conn.execute("""INSERT INTO agent_instance(agent_id,agent_instance_id,runtime_status,last_seen_at)
          VALUES(?,?,?,?) ON CONFLICT(agent_id,agent_instance_id) DO UPDATE SET runtime_status=excluded.runtime_status,last_seen_at=excluded.last_seen_at,updated_at=CURRENT_TIMESTAMP""", (p["agent_id"],p["agent_instance_id"],p.get("runtime_status", "starting"),p.get("last_seen_at"))); self.conn.commit(); return {"agent_id": p["agent_id"], "agent_instance_id": p["agent_instance_id"], "runtime_status": p.get("runtime_status", "starting")}

    def _write(self, caller: Caller, p: dict[str, Any], action: str, target: str, fn):
        key = self._required(p, "idempotency_key")
        old = self.conn.execute("SELECT result_json, request_json FROM operation WHERE idempotency_key=?", (key,)).fetchone()
        request = json.dumps(p, sort_keys=True)
        if old:
            if old["request_json"] != request: raise RegistryError("idempotency_conflict")
            result = json.loads(old["result_json"]); result["duplicate"] = True; return result
        result = fn(); self.conn.execute("INSERT INTO operation (operation_id, idempotency_key, caller_id, action, target_id, request_json, result_json, created_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)", (key, key, caller.caller_id, action, target, request, json.dumps(result, sort_keys=True))); self.conn.commit(); result["duplicate"] = False; return result

    @staticmethod
    def _required(p: dict[str, Any], key: str) -> str:
        value = p.get(key)
        if not isinstance(value, str) or not value: raise RegistryError("missing_required_field")
        return value

    @staticmethod
    def _require(caller: Caller, types: set[str]) -> None:
        if caller.caller_type not in types: raise RegistryError("denied")

    def _require_self_or_owner(self, caller: Caller, principal_id: str | None) -> None:
        if caller.caller_type == "project_owner": return
        if caller.caller_type != "researcher" or caller.caller_id != principal_id: raise RegistryError("denied")
