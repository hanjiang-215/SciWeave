from __future__ import annotations

import json

from research_mapping.config import MappingConfig
from research_mapping.formal_query import FormalQueryService
from research_mapping.sqlite_store import SqliteStore
from research_mapping.terminus_store import TerminusDBStore


def main() -> int:
    config = MappingConfig.from_environment()
    sqlite_store = SqliteStore(config.sqlite_path)
    sqlite_store.initialize()
    terminus_store = TerminusDBStore(
        base_url=config.terminusdb_url,
        token=config.terminusdb_token,
        username=config.terminusdb_username,
        password=config.terminusdb_password,
    )
    service = FormalQueryService(
        sqlite_store=sqlite_store,
        terminus_store=terminus_store,
        terminus_database=config.terminusdb_database,
    )
    result = service.get_current(config.mapping_domain_id)
    print(
        json.dumps(
            {
                "status": result.status,
                "reason_code": result.reason_code,
                "mapping_domain_id": result.mapping_domain_id,
                "formal_revision_id": result.formal_revision_id,
                "store_id": result.store_id,
                "branch_id": result.branch_id,
                "commit_hash": result.commit_hash,
                "node_count": len(result.nodes),
                "edge_count": len(result.edges),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
