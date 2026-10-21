from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import ConfigError

_REQUIRED_VARIABLES = (
    "SCIWEAVE_MAPPING_SQLITE_PATH",
    "SCIWEAVE_MAPPING_DOMAIN_ID",
    "SCIWEAVE_MAPPING_TERMINUSDB_URL",
    "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
)


@dataclass(frozen=True)
class MappingConfig:
    sqlite_path: str
    mapping_domain_id: str
    terminusdb_url: str
    terminusdb_database: str
    terminusdb_store: str
    terminusdb_token: str | None = None
    terminusdb_username: str | None = None
    terminusdb_password: str | None = None

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "MappingConfig":
        env = os.environ if environment is None else environment
        missing = [name for name in _REQUIRED_VARIABLES if not env.get(name)]
        if missing:
            raise ConfigError(
                "missing required environment variables: " + ", ".join(missing)
            )
        token = env.get("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN") or None
        return cls(
            sqlite_path=env["SCIWEAVE_MAPPING_SQLITE_PATH"],
            mapping_domain_id=env["SCIWEAVE_MAPPING_DOMAIN_ID"],
            terminusdb_url=env["SCIWEAVE_MAPPING_TERMINUSDB_URL"],
            terminusdb_database=env["SCIWEAVE_MAPPING_TERMINUSDB_DATABASE"],
            terminusdb_store=env["SCIWEAVE_MAPPING_TERMINUSDB_STORE"],
            terminusdb_token=token,
            terminusdb_username=env.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME") or None,
            terminusdb_password=env.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD") or None,
        )
