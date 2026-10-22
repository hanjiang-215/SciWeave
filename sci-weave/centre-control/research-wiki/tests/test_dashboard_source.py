from __future__ import annotations

import json
import threading
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from llm_wiki.dashboard_source import build_wiki_fragment, create_wiki_dashboard_server
from llm_wiki.formal_domain import FormalResourceReference, WikiFormalQueryResult, WikiReferenceQualification


class WikiDashboardSourceTests(unittest.TestCase):
    def test_projects_formal_references_and_exact_qualifications(self) -> None:
        reference = FormalResourceReference(
            reference_id="ref-1",
            target_resource_version_id="rv-exact-7",
            target_wiki_revision_id=None,
            reference_role="evidence",
            body_locator="paragraph-2",
            qualification=WikiReferenceQualification(
                resource_version_id="rv-exact-7",
                status="approved",
                reason_code="ok",
                use_scope=("experiment-conditions",),
                limitations=("cite-only",),
            ),
        )
        result = WikiFormalQueryResult(
            status="available",
            wiki_domain_id="wiki-1",
            reason_code="ok",
            formal_wiki_revision_id="revision-9",
            terminus_store_id="store",
            database="db",
            formal_branch_id="main",
            formal_commit_hash="commit-9",
            content_digest="digest",
            title="Catalyst design",
            description="Formal description",
            body_markdown="# Private body stays in domain service",
            references=(reference,),
        )
        payload = build_wiki_fragment(result, observed_at="2026-10-22T09:00:00Z")
        self.assertEqual(payload["sourceStatus"], "fresh")
        self.assertEqual(payload["wikiDocuments"][0]["formalRevisionId"], "revision-9")
        self.assertEqual(payload["wikiDocuments"][0]["references"][0]["resourceVersionId"], "rv-exact-7")
        self.assertEqual(payload["wikiDocuments"][0]["references"][0]["qualification"], "approved")
        self.assertEqual(payload["wikiDocuments"][0]["references"][0]["requestedScope"], "experiment-conditions")
        self.assertNotIn("Private body", json.dumps(payload))

    def test_unavailable_formal_query_is_not_projected_as_formal_content(self) -> None:
        result = WikiFormalQueryResult(status="inconsistent", wiki_domain_id="wiki-1", reason_code="pointer_mismatch")
        payload = build_wiki_fragment(result, observed_at="2026-10-22T09:00:00Z")
        self.assertEqual(payload["sourceStatus"], "unavailable")
        self.assertEqual(payload["wikiDocuments"], [])

    def test_candidate_submission_is_exposed_as_candidate_only(self) -> None:
        formal = WikiFormalQueryResult(status="no_formal_revision", wiki_domain_id="wiki-1", reason_code="no_current_pointer")
        candidate = SimpleNamespace(proposal_id="proposal-2", submission_id="submission-2", status="pending", submitted_at="2026-10-22T08:00:00Z")
        payload = build_wiki_fragment(formal, [candidate], observed_at="2026-10-22T09:00:00Z")
        self.assertEqual(payload["wikiCandidates"][0]["state"], "review_pending")
        self.assertEqual(payload["wikiDocuments"], [])
        self.assertEqual(payload["sourceStatus"], "partial")

    def test_projects_exact_reference_qualification_for_isolated_candidate(self) -> None:
        formal = WikiFormalQueryResult(status="no_formal_revision", wiki_domain_id="wiki-1", reason_code="no_current_pointer")
        candidate = {
            "proposal_id": "proposal-9",
            "submission_id": "submission-9",
            "submission_status": "candidate_created",
            "proposal_status": "candidate",
            "merge_request_status": None,
            "title": "Control experiment plan",
            "submitted_at": "2026-10-22T08:00:00Z",
            "references": [{"id": "ref-9", "resourceVersionId": "rv-pinned-9", "qualification": "pending", "requestedScope": "control experiment"}],
        }
        payload = build_wiki_fragment(formal, [candidate], observed_at="2026-10-22T09:00:00Z")
        self.assertEqual(payload["wikiCandidates"][0]["title"], "Control experiment plan")
        self.assertEqual(payload["wikiCandidates"][0]["references"][0]["resourceVersionId"], "rv-pinned-9")
        self.assertEqual(payload["wikiCandidates"][0]["references"][0]["qualification"], "pending")
        self.assertEqual(payload["wikiCandidates"][0]["state"], "candidate")

    def test_candidate_states_distinguish_review_approval_and_formalization(self) -> None:
        formal = WikiFormalQueryResult(status="available", wiki_domain_id="wiki-1", reason_code="ok", formal_wiki_revision_id="rev", terminus_store_id="s", database="d", formal_branch_id="main", formal_commit_hash="c", content_digest="digest", body_markdown="# title")
        candidates = [
            {"proposal_id": "p1", "submission_id": "s1", "submission_status": "candidate_created", "proposal_status": "candidate", "merge_request_status": "ready_for_owner", "owner_decision": "pending", "candidate_snapshot_status": "confirmed"},
            {"proposal_id": "p2", "submission_id": "s2", "submission_status": "candidate_created", "proposal_status": "candidate", "merge_request_status": "approved", "owner_decision": "approved", "candidate_snapshot_status": "unavailable"},
            {"proposal_id": "p3", "submission_id": "s3", "submission_status": "candidate_created", "proposal_status": "merged", "merge_request_status": "merged", "owner_decision": "approved", "candidate_snapshot_status": "confirmed"},
        ]
        payload = build_wiki_fragment(formal, candidates, observed_at="2026-10-22T09:00:00Z")
        self.assertEqual([item["state"] for item in payload["wikiCandidates"]], ["review_pending", "approved_pending_formalization", "formalized"])
        self.assertEqual(payload["sourceStatus"], "partial")

    def test_http_source_is_read_only_and_can_require_token(self) -> None:
        fragment = {"observedAt": "2026-10-22T09:00:00Z", "sourceStatus": "fresh", "wikiDocuments": [], "wikiCandidates": [], "events": []}
        server = create_wiki_dashboard_server(lambda: fragment, host="127.0.0.1", port=0, token="wiki-read-only")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base}/api/dashboard/source/wiki")
            self.assertEqual(raised.exception.code, 401)
            request = Request(f"{base}/api/dashboard/source/wiki", headers={"Authorization": "Bearer wiki-read-only"})
            with urlopen(request) as response:
                self.assertEqual(json.loads(response.read())["sourceStatus"], "fresh")
            with self.assertRaises(HTTPError) as raised:
                urlopen(Request(f"{base}/api/dashboard/source/wiki", data=b"{}", method="POST"))
            self.assertEqual(raised.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
