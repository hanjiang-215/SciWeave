from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


_FORBIDDEN_FIELDS = {
    "executor_refs",
    "allowed_mcp",
    "readable_task_nodes",
    "writable_namespaces",
    "credential",
    "credentials",
    "host",
    "hostname",
}
_PRINCIPAL_STATUSES = {"active", "disabled"}
_AGENT_STATUSES = {"active", "retired"}
_INSTANCE_STATUSES = {"starting", "online", "offline", "revoked"}


@dataclass(frozen=True)
class Caller:
    caller_id: str
    caller_type: str
    principal_id: str | None = None
    service_role: str | None = None

    def held_principal_id(self) -> str | None:
        if self.principal_id:
            return self.principal_id
        if self.caller_type == "researcher":
            return self.caller_id
        return None


class RegistryError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RegistryService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.conn = connection
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS principal (
              principal_id TEXT PRIMARY KEY,
              role TEXT NOT NULL,
              contact_email TEXT,
              status TEXT NOT NULL,
              contact_version INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS workflow_agent (
              agent_id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              principal_id TEXT,
              workflow_kind TEXT NOT NULL,
              created_by TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS agent_instance (
              agent_id TEXT NOT NULL,
              agent_instance_id TEXT NOT NULL,
              runtime_status TEXT NOT NULL,
              last_seen_at TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (agent_id, agent_instance_id),
              FOREIGN KEY (agent_id) REFERENCES workflow_agent(agent_id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS agent_instance_id_unique
              ON agent_instance(agent_instance_id);
            CREATE TABLE IF NOT EXISTS status_event (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              target_type TEXT NOT NULL,
              target_id TEXT NOT NULL,
              status TEXT NOT NULL,
              recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS operation (
              operation_id TEXT PRIMARY KEY,
              idempotency_key TEXT NOT NULL UNIQUE,
              caller_id TEXT NOT NULL,
              action TEXT NOT NULL,
              target_id TEXT NOT NULL,
              request_json TEXT NOT NULL,
              result_json TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    def register_principal(self, caller: Caller, payload: dict[str, Any]) -> dict[str, Any]:
        self._require(caller, {"project_owner"})
        self._reject_forbidden(payload)
        principal_id = self._required(payload, "principal_id")
        role = payload.get("role")
        if role not in {"researcher", "project_owner"}:
            raise RegistryError("invalid_role")
        status = payload.get("status", "active")
        if status not in _PRINCIPAL_STATUSES:
            raise RegistryError("invalid_status")
        return self._write(caller, payload, "register_principal", principal_id, lambda: self._upsert_principal(payload))

    def register_workflow_agent(self, caller: Caller, payload: dict[str, Any]) -> dict[str, Any]:
        self._reject_forbidden(payload)
        kind = payload.get("kind")
        principal_id = payload.get("principal_id")
        if kind == "endpoint":
            if caller.caller_type != "project_owner":
                self._require_self_or_owner(caller, principal_id if isinstance(principal_id, str) else None)
            if not isinstance(principal_id, str) or not principal_id:
                raise RegistryError("principal_required")
        elif kind == "centre":
            self._require(caller, {"project_owner"})
            if principal_id not in (None, ""):
                raise RegistryError("centre_principal_must_be_empty")
        else:
            raise RegistryError("invalid_agent_kind")
        status = payload.get("status", "active")
        if status not in _AGENT_STATUSES:
            raise RegistryError("invalid_status")
        agent_id = self._required(payload, "agent_id")
        self._required(payload, "workflow_id")
        self._required(payload, "workflow_kind")
        return self._write(caller, payload, "register_workflow_agent", agent_id, lambda: self._upsert_agent(caller, payload))

    def register_agent_instance(self, caller: Caller, payload: dict[str, Any]) -> dict[str, Any]:
        if caller.caller_type == "service":
            raise RegistryError("denied")
        self._reject_forbidden(payload)
        agent_id = self._required(payload, "agent_id")
        instance_id = self._required(payload, "agent_instance_id")
        runtime_status = payload.get("runtime_status", "starting")
        if runtime_status not in _INSTANCE_STATUSES:
            raise RegistryError("invalid_status")
        try:
            row = self.conn.execute(
                "SELECT principal_id, kind FROM workflow_agent WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise RegistryError("registry_unavailable") from exc
        if row is None:
            raise RegistryError("agent_not_found")
        if row["kind"] == "centre":
            self._require(caller, {"project_owner"})
        else:
            self._require_self_or_owner(caller, row["principal_id"])
        target = f"{agent_id}:{instance_id}"
        return self._write(caller, payload, "register_agent_instance", target, lambda: self._upsert_instance(payload))

    def get_principal_contact(self, caller: Caller, payload: dict[str, Any]) -> dict[str, Any]:
        if not (caller.caller_type == "project_owner" or caller.service_role == "email"):
            raise RegistryError("denied")
        principal_id = self._required(payload, "principal_id")
        try:
            row = self.conn.execute("SELECT * FROM principal WHERE principal_id=?", (principal_id,)).fetchone()
        except sqlite3.Error as exc:
            raise RegistryError("registry_unavailable") from exc
        if row is None:
            raise RegistryError("principal_not_found")
        if row["status"] != "active":
            raise RegistryError("contact_disabled")
        if not row["contact_email"]:
            raise RegistryError("contact_missing")
        return {
            "principal_id": principal_id,
            "contact_email": row["contact_email"],
            "status": row["status"],
            "contact_version": f"contact:{principal_id}:{row['contact_version']}",
        }

    def get_agent_registration(self, caller: Caller, payload: dict[str, Any]) -> dict[str, Any]:
        if not (caller.caller_type == "project_owner" or caller.service_role == "centre"):
            raise RegistryError("denied")
        agent_id = self._required(payload, "agent_id")
        try:
            agent = self.conn.execute("SELECT * FROM workflow_agent WHERE agent_id=?", (agent_id,)).fetchone()
            instances = self.conn.execute(
                "SELECT * FROM agent_instance WHERE agent_id=? ORDER BY agent_instance_id",
                (agent_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise RegistryError("registry_unavailable") from exc
        if agent is None:
            raise RegistryError("agent_not_found")
        return {
            "agent": dict(agent),
            "instances": [dict(row) for row in instances],
            "status_history": self._history("workflow_agent", agent_id),
            "instance_status_history": {
                row["agent_instance_id"]: self._history("agent_instance", f"{agent_id}:{row['agent_instance_id']}")
                for row in instances
            },
        }

    def health(self, caller: Caller) -> dict[str, str]:
        self._require(caller, {"researcher", "project_owner", "service"})
        return {"status": "ready", "service": "registry", "storage": "ready"}

    def _upsert_principal(self, payload: dict[str, Any]) -> dict[str, Any]:
        principal_id = payload["principal_id"]
        role = payload["role"]
        current = self.conn.execute(
            "SELECT status, contact_email FROM principal WHERE principal_id=?",
            (principal_id,),
        ).fetchone()
        status = payload.get("status", "active")
        if current is not None and payload.get("contact_email") is None:
            email = current["contact_email"]
        else:
            email = payload.get("contact_email")
        self.conn.execute(
            """
            INSERT INTO principal(principal_id, role, contact_email, status)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(principal_id) DO UPDATE SET
              role=excluded.role,
              contact_email=excluded.contact_email,
              status=excluded.status,
              contact_version=CASE
                WHEN principal.contact_email IS NOT excluded.contact_email
                  OR principal.status IS NOT excluded.status
                  OR principal.role IS NOT excluded.role
                THEN principal.contact_version + 1
                ELSE principal.contact_version
              END,
              updated_at=CURRENT_TIMESTAMP
            """,
            (principal_id, role, email, status),
        )
        if current is None or current["status"] != status:
            self._append_status("principal", principal_id, status)
        return {"principal_id": principal_id, "status": status}

    def _upsert_agent(self, caller: Caller, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = payload["agent_id"]
        current = self.conn.execute(
            "SELECT principal_id, kind, status FROM workflow_agent WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if current is not None and (current["kind"] != payload["kind"] or current["principal_id"] != payload.get("principal_id")):
            raise RegistryError("agent_owner_conflict")
        status = payload.get("status", "active")
        self.conn.execute(
            """
            INSERT INTO workflow_agent(
              agent_id, workflow_id, kind, principal_id, workflow_kind, created_by, status
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
              workflow_id=excluded.workflow_id,
              workflow_kind=excluded.workflow_kind,
              status=excluded.status,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                agent_id,
                payload["workflow_id"],
                payload["kind"],
                payload.get("principal_id"),
                payload["workflow_kind"],
                payload.get("created_by") or caller.caller_id,
                status,
            ),
        )
        if current is None or current["status"] != status:
            self._append_status("workflow_agent", agent_id, status)
        return {"agent_id": agent_id, "status": status}

    def _upsert_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = payload["agent_id"]
        instance_id = payload["agent_instance_id"]
        runtime_status = payload.get("runtime_status", "starting")
        bound = self.conn.execute(
            "SELECT agent_id, runtime_status, last_seen_at FROM agent_instance WHERE agent_instance_id=?",
            (instance_id,),
        ).fetchone()
        if bound is not None and bound["agent_id"] != agent_id:
            raise RegistryError("instance_identity_conflict")
        if bound is not None and payload.get("last_seen_at") is None:
            last_seen_at = bound["last_seen_at"]
        else:
            last_seen_at = payload.get("last_seen_at")
        self.conn.execute(
            """
            INSERT INTO agent_instance(agent_id, agent_instance_id, runtime_status, last_seen_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(agent_id, agent_instance_id) DO UPDATE SET
              runtime_status=excluded.runtime_status,
              last_seen_at=excluded.last_seen_at,
              updated_at=CURRENT_TIMESTAMP
            """,
            (agent_id, instance_id, runtime_status, last_seen_at),
        )
        if bound is None or bound["runtime_status"] != runtime_status:
            self._append_status("agent_instance", f"{agent_id}:{instance_id}", runtime_status)
        return {"agent_id": agent_id, "agent_instance_id": instance_id, "runtime_status": runtime_status}

    def _write(self, caller: Caller, payload: dict[str, Any], action: str, target: str, operation):
        key = self._required(payload, "idempotency_key")
        try:
            previous = self.conn.execute(
                "SELECT result_json, request_json FROM operation WHERE idempotency_key=?",
                (key,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise RegistryError("registry_unavailable") from exc
        request = json.dumps(payload, sort_keys=True)
        if previous is not None:
            if previous["request_json"] != request:
                raise RegistryError("idempotency_conflict")
            result = json.loads(previous["result_json"])
            result["duplicate"] = True
            return result
        try:
            self.conn.execute("BEGIN")
            result = operation()
            self.conn.execute(
                """
                INSERT INTO operation(
                  operation_id, idempotency_key, caller_id, action, target_id, request_json, result_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (key, key, caller.caller_id, action, target, request, json.dumps(result, sort_keys=True)),
            )
            self.conn.commit()
        except RegistryError:
            self.conn.rollback()
            raise
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise RegistryError("registry_unavailable") from exc
        result["duplicate"] = False
        return result

    def _history(self, target_type: str, target_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT status FROM status_event WHERE target_type=? AND target_id=? ORDER BY event_id",
            (target_type, target_id),
        ).fetchall()
        return [row["status"] for row in rows]

    def _append_status(self, target_type: str, target_id: str, status: str) -> None:
        self.conn.execute(
            "INSERT INTO status_event(target_type, target_id, status) VALUES(?, ?, ?)",
            (target_type, target_id, status),
        )

    @staticmethod
    def _required(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise RegistryError("missing_required_field")
        return value

    @staticmethod
    def _reject_forbidden(payload: dict[str, Any]) -> None:
        if _FORBIDDEN_FIELDS.intersection(payload):
            raise RegistryError("forbidden_field")

    @staticmethod
    def _require(caller: Caller, types: set[str]) -> None:
        if caller.caller_type not in types:
            raise RegistryError("denied")

    def _require_self_or_owner(self, caller: Caller, principal_id: str | None) -> None:
        if caller.caller_type == "project_owner":
            return
        if caller.caller_type == "researcher" and principal_id and caller.held_principal_id() == principal_id:
            return
        raise RegistryError("denied")
