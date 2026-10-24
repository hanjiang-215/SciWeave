from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RegistryConfig:
    host: str
    port: int
    sqlite_path: str
    audit_sqlite_path: str
    bearer_token: str

    @classmethod
    def from_environment(cls) -> "RegistryConfig":
        return cls(
            host=os.environ.get("SCIWEAVE_REGISTRY_HOST", "127.0.0.1"),
            port=int(os.environ.get("SCIWEAVE_REGISTRY_PORT", "0")),
            sqlite_path=os.environ.get("SCIWEAVE_REGISTRY_SQLITE_PATH", ":memory:"),
            audit_sqlite_path=os.environ.get("SCIWEAVE_REGISTRY_AUDIT_SQLITE_PATH", ":memory:"),
            bearer_token=os.environ.get("SCIWEAVE_REGISTRY_BEARER_TOKEN", ""),
        )
