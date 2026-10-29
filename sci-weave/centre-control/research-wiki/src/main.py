from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict

from llm_wiki.config import WikiConfig
from llm_wiki.dashboard_source import build_wiki_fragment, project_candidate_references, run_wiki_dashboard_from_environment
from llm_wiki.formal_query import WikiFormalQueryService
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.governance_events import create_governance_publisher
from llm_wiki.resource_review import ResourceReviewService, SqliteResourceVersionLocationSource
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.terminus_store import TerminusDBWikiCandidateStore

logger = logging.getLogger("llm_wiki")

# B12: sentinel so an empty store (no content anywhere) initializes a default
# formal revision, while a store whose pointers live under a different domain
# than the configured one is a mismatch we surface instead of silently seeding.
def _warn_if_domain_mismatch(sqlite_store: SqliteStore, configured_domain: str) -> bool:
    """Return True when the store has content under other domains only.

    Signals a config/data domain mismatch (B12): the dashboard queries
    ``configured_domain`` and would report ``no_current_pointer`` even though
    formal revisions exist under a different domain id.
    """
    known = sqlite_store.list_known_domains()
    others = [domain for domain in known if domain != configured_domain]
    if known and configured_domain not in known and others:
        logger.warning(
            "wiki domain mismatch: configured SCIWEAVE_WIKI_DOMAIN_ID=%r has no current "
            "formal pointer, but the store has formal revisions under %s; the dashboard "
            "will report no_current_pointer. Set SCIWEAVE_WIKI_DOMAIN_ID to the data domain.",
            configured_domain,
            others,
        )
        return True
    return False


def _health_report(sqlite_store: SqliteStore, configured_domain: str):
    """Return a ``/health`` provider that flags a config/data domain mismatch (B12).

    The dashboard queries ``configured_domain``; if formal revisions live only
    under other domains the dashboard reports ``no_current_pointer`` while the
    process still looks healthy. Surface that as ``degraded`` with the domains
    actually present so an operator can fix the configuration.
    """
    def report() -> dict[str, object]:
        known = sqlite_store.list_known_domains()
        others = [domain for domain in known if domain != configured_domain]
        has_pointer = configured_domain in known
        if known and not has_pointer and others:
            return {
                "status": "degraded",
                "wiki_domain_id": configured_domain,
                "reason_code": "wiki_domain_mismatch",
                "known_domains": known,
                "detail": (
                    f"configured domain {configured_domain!r} has no current formal pointer, "
                    f"but formal revisions exist under {others}; the dashboard will report "
                    "no_current_pointer. Set SCIWEAVE_WIKI_DOMAIN_ID to the data domain."
                ),
            }
        return {"wiki_domain_id": configured_domain, "formal_pointer_present": has_pointer}

    return report


def _build_candidate_store(config: WikiConfig) -> TerminusDBWikiCandidateStore:
    return TerminusDBWikiCandidateStore(
        store_id=config.terminusdb_store,
        database=config.terminusdb_database,
        base_url=config.terminusdb_url,
        token=config.terminusdb_token,
        username=config.terminusdb_username,
        password=config.terminusdb_password,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv if argv is None else argv
    config = WikiConfig.from_environment()
    sqlite_store = SqliteStore(config.sqlite_path)
    sqlite_store.initialize()
    # ai4-4g9s: ``reap-branches`` deletes candidate branches no longer backing an
    # active submission. Opt-in and explicit; supports --dry-run to preview.
    if len(arguments) > 1 and arguments[1] == "reap-branches":
        from llm_wiki.branch_reaper import reap_candidate_branches

        dry_run = "--dry-run" in arguments
        store = _build_candidate_store(config)
        result = reap_candidate_branches(
            sqlite_store=sqlite_store,
            terminus_store=store,
            wiki_domain_id=config.domain_id,
            dry_run=dry_run,
        )
        print(json.dumps({
            "dry_run": dry_run,
            "deleted": result.deleted,
            "failed": result.failed,
            "kept_active": result.kept_active,
            "skipped": result.skipped,
        }, ensure_ascii=False))
        return 0 if not result.failed else 1
    # ai4-n7js: the candidate -> review -> formalize chain needs the candidate
    # store. With the read-only resource store every write tool answered
    # result_unknown / candidate_head_changed and no candidate could be
    # created, approved or formalized -- silently, because those failures are
    # result codes rather than exceptions.
    terminus_store = _build_candidate_store(config)
    if sqlite_store.get_current_formal_revision_id(config.domain_id) is None:
        if _warn_if_domain_mismatch(sqlite_store, config.domain_id):
            # Content exists under another domain: do not seed a fresh default
            # for the wrongly-configured domain (that would hide the mismatch
            # and leave the real data unreachable from the dashboard).
            pass
        else:
            domain_key = hashlib.sha256(config.domain_id.encode("utf-8")).hexdigest()
            initial = terminus_store.ensure_default_formal_snapshot(config.domain_id)
            if initial.status != "confirmed":
                raise RuntimeError(f"wiki default formal snapshot initialization failed: {initial.reason_code}")
            sqlite_store.ensure_initial_formal_revision(
                formal_revision_id="wiki-default-" + domain_key,
                result_id="wiki-default-result-" + domain_key,
                wiki_domain_id=config.domain_id,
                terminus_store_id=initial.store_id,
                formal_branch_id=initial.branch_id,
                formal_commit_hash=initial.commit_hash,
            )
    service = ResourceReviewService(
        sqlite_store=sqlite_store,
        terminus_store=terminus_store,
        location_source=SqliteResourceVersionLocationSource(sqlite_store),
    )
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
        # ai4-0hdz: the MCP endpoint is the owner-facing surface, so the first
        # formal revision is created through a guarded tool there rather than a
        # startup side effect.
        from llm_wiki.bootstrap import WikiBootstrapService

        bootstrap_service = WikiBootstrapService(
            sqlite_store=sqlite_store,
            terminus_store=terminus_store,
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
            bootstrap_service=bootstrap_service,
            # ai4-u5e6: 与 research-map 对称。不接线时 wiki 的候选提交与正式发布
            # 不产生任何事件，下游（Centre Agent、交接协调）只能靠快照扫描。
            governance_events=create_governance_publisher(config.governance_kafka_bootstrap),
        )
        return run_wiki_management_server_from_config(
            config, management, health=_health_report(sqlite_store, config.domain_id)
        )
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
