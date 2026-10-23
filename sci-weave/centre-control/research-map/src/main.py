from __future__ import annotations

import json
import os

from research_mapping.candidate_submission import MappingCandidateService
from research_mapping.config import MappingConfig
from research_mapping.dashboard_source import run_mapping_dashboard_from_environment
from research_mapping.formal_query import FormalQueryService
from research_mapping.formalization import MappingFormalizationService
from research_mapping.management import MappingManagementService, open_audit_database
from research_mapping.management_mcp import run_management_server_from_config
from research_mapping.review import MappingReviewService
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
        store_id=config.terminusdb_store,
        database=config.terminusdb_database,
    )
    service = FormalQueryService(
        sqlite_store=sqlite_store,
        terminus_store=terminus_store,
        terminus_database=config.terminusdb_database,
    )
    if os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_MODE") == "1":
        return run_mapping_dashboard_from_environment(service, config.mapping_domain_id)
    if config.mcp_host is not None:
        if not config.mcp_tokens:
            raise RuntimeError("SCIWEAVE_MAPPING_MCP_TOKENS_JSON is required for the management MCP endpoint")
        capabilities = config.caller_capabilities or {}
        audit = None
        if config.audit_sqlite_path:
            audit = open_audit_database(config.audit_sqlite_path)
        candidate_service = MappingCandidateService(
            sqlite_store=sqlite_store,
            terminus_store=terminus_store,
            terminus_database=config.terminusdb_database,
        )
        review_service = MappingReviewService(
            sqlite_store, terminus_store, terminus_database=config.terminusdb_database,
        )
        formalization_service = MappingFormalizationService(
            sqlite_store, terminus_store, terminus_database=config.terminusdb_database,
            is_project_owner=lambda actor, domain: "formalize" in capabilities.get(actor, ()),
        )
        management = MappingManagementService(
            formal_query=service,
            candidate_service=candidate_service,
            caller_capabilities=capabilities,
            audit_connection=audit,
            review_service=review_service,
            formalization_service=formalization_service,
        )
        return run_management_server_from_config(config, management)
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
