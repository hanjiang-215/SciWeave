from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenIdentity:
    caller_id: str
    caller_type: str
    principal_id: str | None = None
    service_role: str | None = None


@dataclass(frozen=True)
class RegistryConfig:
    host: str
    port: int
    sqlite_path: str
    audit_sqlite_path: str
    issuer_url: str
    resource_url: str
    token_identities: dict[str, TokenIdentity]

    @classmethod
    def from_environment(cls) -> "RegistryConfig":
        required = (
            "SCIWEAVE_REGISTRY_SQLITE_PATH",
            "SCIWEAVE_AUDIT_SQLITE_PATH",
            "SCIWEAVE_REGISTRY_HOST",
            "SCIWEAVE_REGISTRY_PORT",
            "SCIWEAVE_REGISTRY_ISSUER_URL",
            "SCIWEAVE_REGISTRY_RESOURCE_URL",
            "SCIWEAVE_REGISTRY_TOKENS_JSON",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(f"missing required Registry configuration: {', '.join(missing)}")
        try:
            raw_tokens = json.loads(os.environ["SCIWEAVE_REGISTRY_TOKENS_JSON"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("SCIWEAVE_REGISTRY_TOKENS_JSON must be a JSON object") from exc
        if not isinstance(raw_tokens, dict) or not raw_tokens:
            raise ValueError("SCIWEAVE_REGISTRY_TOKENS_JSON must contain at least one token")
        identities: dict[str, TokenIdentity] = {}
        for token, raw_identity in raw_tokens.items():
            if not isinstance(token, str) or not token or not isinstance(raw_identity, dict):
                raise ValueError("invalid Registry token identity entry")
            caller_id = raw_identity.get("caller_id")
            caller_type = raw_identity.get("caller_type")
            principal_id = raw_identity.get("principal_id")
            service_role = raw_identity.get("service_role")
            if not isinstance(caller_id, str) or not caller_id:
                raise ValueError("Registry token identity requires caller_id")
            if caller_type not in {"researcher", "project_owner", "service"}:
                raise ValueError("Registry token identity has invalid caller_type")
            if principal_id is not None and not isinstance(principal_id, str):
                raise ValueError("principal_id must be a string when provided")
            if caller_type == "service":
                if service_role not in {"centre", "email"}:
                    raise ValueError("service token identity requires service_role centre or email")
            elif service_role is not None:
                raise ValueError("service_role is only valid for service tokens")
            identities[token] = TokenIdentity(caller_id, caller_type, principal_id, service_role)
        return cls(
            host=os.environ["SCIWEAVE_REGISTRY_HOST"],
            port=int(os.environ["SCIWEAVE_REGISTRY_PORT"]),
            sqlite_path=os.environ["SCIWEAVE_REGISTRY_SQLITE_PATH"],
            audit_sqlite_path=os.environ["SCIWEAVE_AUDIT_SQLITE_PATH"],
            issuer_url=os.environ["SCIWEAVE_REGISTRY_ISSUER_URL"],
            resource_url=os.environ["SCIWEAVE_REGISTRY_RESOURCE_URL"],
            token_identities=identities,
        )
