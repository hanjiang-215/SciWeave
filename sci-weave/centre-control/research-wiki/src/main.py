from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from llm_wiki.config import WikiConfig
from llm_wiki.dashboard_source import build_wiki_fragment, project_candidate_references, run_wiki_dashboard_from_environment
from llm_wiki.formal_query import WikiFormalQueryService
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.resource_review import ResourceReviewService
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.terminus_store import TerminusDBResourceStore


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv if argv is None else argv
    config = WikiConfig.from_environment()
    sqlite_store = SqliteStore(config.sqlite_path)
    sqlite_store.initialize()
    terminus_store = TerminusDBResourceStore(
        base_url=config.terminusdb_url,
        token=config.terminusdb_token,
        username=config.terminusdb_username,
        password=config.terminusdb_password,
    )
    service = ResourceReviewService(sqlite_store=sqlite_store, terminus_store=terminus_store)
    formal_query = WikiFormalQueryService(
        sqlite_store=sqlite_store,
        terminus_store=terminus_store,
        terminus_database=config.terminusdb_database,
        resource_review_service=service,
    )
    if os.environ.get("SCIWEAVE_WIKI_DASHBOARD_MODE") == "1":
        def read_dashboard_fragment():
            candidates = []
            for row in sqlite_store.list_dashboard_candidates(config.domain_id):
                candidate = dict(row)
                candidate["candidate_snapshot_status"] = "pending"
                if candidate.get("terminus_store_id") and candidate.get("branch_id") and candidate.get("commit_hash"):
                    try:
                        snapshot = terminus_store.read_exact_snapshot(
                            candidate["terminus_store_id"],
                            config.terminusdb_database,
                            candidate["branch_id"],
                            candidate["commit_hash"],
                        )
                    except Exception:
                        snapshot = None
                    if isinstance(snapshot, WikiSnapshotRead) and snapshot.status == "confirmed" and (
                        snapshot.store_id, snapshot.database, snapshot.branch_id, snapshot.commit_hash
                    ) == (candidate["terminus_store_id"], config.terminusdb_database, candidate["branch_id"], candidate["commit_hash"]):
                        documents = list(snapshot.documents)
                        revision = next((document for document in documents if document.get("@type") == "WikiRevision"), {})
                        candidate["candidate_snapshot_status"] = "confirmed"
                        candidate["title"] = revision.get("title") or "Wiki 候选文档"
                        candidate["references"] = project_candidate_references(
                            documents,
                            lambda version_id, scope: service.get_current_qualification(version_id, scope),
                        )
                    else:
                        candidate["candidate_snapshot_status"] = "unavailable"
                candidates.append(candidate)
            return build_wiki_fragment(formal_query.get_current(config.domain_id), candidates)

        return run_wiki_dashboard_from_environment(read_dashboard_fragment)
    if config.mcp_host is not None:
        from llm_wiki.candidate_submission import WikiCandidateService
        from llm_wiki.formalization import WikiFormalizationService
        from llm_wiki.management import WikiManagementService, open_audit_database
        from llm_wiki.management_mcp import run_wiki_management_server_from_config
        from llm_wiki.review import WikiReviewService
        if not config.mcp_tokens:
            raise RuntimeError("SCIWEAVE_WIKI_MCP_TOKENS_JSON is required for the management MCP endpoint")
        capabilities = config.caller_capabilities or {}
        audit = None
        if config.audit_sqlite_path:
            audit = open_audit_database(config.audit_sqlite_path)
        candidate_service = WikiCandidateService(
            sqlite_store=sqlite_store,
            terminus_store=terminus_store,
            resource_review_service=service,
            terminus_database=config.terminusdb_database,
        )
        from llm_wiki.candidate_reader import WikiCandidateReader

        candidate_reader = WikiCandidateReader(
            sqlite_store=sqlite_store,
            terminus_store=terminus_store,
            terminus_database=config.terminusdb_database,
        )
        class _OwnerVerifier:
            def verify_owner(self, actor_id, wiki_domain_id):
                return "formalize" in capabilities.get(actor_id, ())

        review_service = WikiReviewService(
            sqlite_store=sqlite_store,
            terminus_store=terminus_store,
            terminus_database=config.terminusdb_database,
            resource_review_service=service,
            owner_authorization_verifier=_OwnerVerifier(),
        )
        formalization_service = WikiFormalizationService(
            sqlite_store=sqlite_store,
            terminus_store=terminus_store,
            terminus_database=config.terminusdb_database,
            resource_review_service=service,
            owner_authorization_verifier=_OwnerVerifier(),
        )
        from llm_wiki.prereview import WikiPrereviewLog

        prereview_log = WikiPrereviewLog(
            sqlite_store, rules_dir=config.prereview_rules_dir
        )
        from llm_wiki.merged_candidate import WikiMergedCandidateService

        merged_candidate_service = WikiMergedCandidateService(
            sqlite_store, candidate_service,
            service_name="wiki-management",
        )
        management = WikiManagementService(
            formal_query=formal_query,
            candidate_service=candidate_service,
            caller_capabilities=capabilities,
            audit_connection=audit,
            review_service=review_service,
            formalization_service=formalization_service,
            sqlite_store=sqlite_store,
            candidate_reader=candidate_reader,
            prereview_log=prereview_log,
            merged_candidate_service=merged_candidate_service,
        )
        return run_wiki_management_server_from_config(config, management)
    if len(arguments) > 1:
        qualification = service.get_current_qualification(arguments[1])
        print(json.dumps(asdict(qualification), ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "status": "ready",
                    "domain_id": config.domain_id,
                    "resource_version_read": "unavailable",
                    "reason_code": "exact_version_location_unknown",
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
