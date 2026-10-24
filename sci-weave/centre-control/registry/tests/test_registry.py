import json
import sqlite3
import urllib.request

import pytest

from registry.http_server import create_registry_server
from registry.config import RegistryConfig
from registry.service import Caller, RegistryError, RegistryService


def service():
    return RegistryService(sqlite3.connect(":memory:"))


def test_principal_and_contact():
    s = service()
    result = s.register_principal(Caller("po", "project_owner"), {"principal_id":"person:a", "role":"researcher", "contact_email":"a@example.test", "idempotency_key":"p1"})
    assert result["duplicate"] is False
    assert s.get_principal_contact(Caller("service:email", "service"), {"principal_id":"person:a"})["contact_email"] == "a@example.test"


def test_researcher_can_register_only_self_endpoint_agent():
    s = service()
    with pytest.raises(RegistryError) as error:
        s.register_workflow_agent(Caller("person:a", "researcher"), {"agent_id":"agent:x", "workflow_id":"wf:x", "kind":"endpoint", "principal_id":"person:b", "workflow_kind":"task", "idempotency_key":"a1"})
    assert error.value.code == "denied"
    result = s.register_workflow_agent(Caller("person:a", "researcher"), {"agent_id":"agent:x", "workflow_id":"wf:x", "kind":"endpoint", "principal_id":"person:a", "workflow_kind":"task", "idempotency_key":"a2"})
    assert result["agent_id"] == "agent:x"


def test_idempotency_conflict_and_multiple_instances():
    s = service()
    s.register_principal(Caller("po", "project_owner"), {"principal_id":"person:a", "role":"researcher", "idempotency_key":"p"})
    s.register_workflow_agent(Caller("person:a", "researcher"), {"agent_id":"agent:x", "workflow_id":"wf:x", "kind":"endpoint", "principal_id":"person:a", "workflow_kind":"task", "idempotency_key":"a"})
    duplicate = s.register_agent_instance(Caller("person:a", "researcher"), {"agent_id":"agent:x", "agent_instance_id":"i1", "runtime_status":"online", "idempotency_key":"i"})
    again = s.register_agent_instance(Caller("person:a", "researcher"), {"agent_id":"agent:x", "agent_instance_id":"i1", "runtime_status":"online", "idempotency_key":"i"})
    assert again["duplicate"] is True
    assert duplicate["agent_instance_id"] == "i1"


def test_audit_record_is_separate_from_registry_facts():
    s = service()
    assert "executor_refs" not in {row[1] for row in s.conn.execute("PRAGMA table_info(workflow_agent)")}
