from __future__ import annotations

import os
import tempfile
import unittest

from llm_wiki.config import ConfigError, WikiConfig
from llm_wiki.domain import (
    AuthorityContext,
    ResourceVersionLocation,
    ResourceVersionRead,
    ResourceVersionSnapshot,
)
from llm_wiki.resource_review import ResourceReviewService
from llm_wiki.sqlite_store import SqliteStore


VERSION = "rv-1"
OWNER = "owner-1"
LOCATION = ResourceVersionLocation(
    store_id="admin",
    database="wiki",
    branch_id="main",
    commit_hash="c" * 40,
)


def snapshot(**overrides) -> ResourceVersionSnapshot:
    values = {
        "resource_version_id": VERSION,
        "resource_id": "resource-1",
        "owner_id": OWNER,
        "content_digest": "a" * 64,
        "snapshot_digest": "c" * 64,
        "content_checksum_algorithm": "sha256",
        "source_locator": "doi:10.0000/example",
        "source_external_id": "external-1",
        "external_version_id": "upstream-v1",
        "current_access_locator": "https://example.org/items/1",
        "availability_status": "available",
        "availability_checked_at": "2026-10-20T00:00:00Z",
        "generated_at": "2026-10-19T00:00:00Z",
        "generated_by": "task-agent-1",
        "generated_by_task_id": "task-1",
        "license": "CC-BY-4.0",
        "attribution": "Example Lab",
        "handling_mode": "direct_query",
        "availability_status": "available",
    }
    values.update(overrides)
    return ResourceVersionSnapshot(**values)


class FakeResourceStore:
    def __init__(self, outcome: ResourceVersionRead):
        self.outcome = outcome
        self.calls: list[tuple[ResourceVersionLocation, str]] = []

    def read_resource_version(
        self, location: ResourceVersionLocation, resource_version_id: str
    ) -> ResourceVersionRead:
        self.calls.append((location, resource_version_id))
        return self.outcome


class FakeLocationSource:
    def __init__(self, location: ResourceVersionLocation | None = LOCATION):
        self.location = location
        self.calls: list[str] = []

    def locate(self, resource_version_id: str) -> ResourceVersionLocation | None:
        self.calls.append(resource_version_id)
        return self.location


class FakeAuthorizer:
    def __init__(self, allowed: set[tuple[str, str, str, str]]):
        self.allowed = allowed
        self.calls: list[tuple[str, str, str, str]] = []

    def verify(
        self,
        actor_id: str,
        resource_version_id: str,
        owner_id: str,
        authority_context: AuthorityContext,
    ) -> bool:
        key = (
            actor_id,
            resource_version_id,
            owner_id,
            authority_context.authority_reference,
        )
        self.calls.append(key)
        return key in self.allowed


class ResourceReviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(os.path.join(self._tmp.name, "wiki.db"))
        self.store.initialize()
        self.resources = FakeResourceStore(
            ResourceVersionRead.confirmed(snapshot())
        )
        self.locations = FakeLocationSource()

    def service(self, authorizer=None) -> ResourceReviewService:
        return ResourceReviewService(
            sqlite_store=self.store,
            terminus_store=self.resources,
            authorizer=authorizer,
            location_source=self.locations,
            clock=lambda: "2026-10-21T00:00:00Z",
        )

    def test_owner_approval_is_appended_with_full_evidence(self) -> None:
        outcome = self.service().record_decision(
            VERSION,
            OWNER,
            "approved",
            reason="identity, license and checksum checked",
            evidence="doi-evidence-1",
            scope=("reference",),
        )

        self.assertTrue(outcome.recorded)
        self.assertEqual(outcome.reason_code, "decision_recorded")
        self.assertEqual(outcome.qualification.status, "approved")
        self.assertIsNotNone(outcome.review_id)

        reviews = self.store.list_reviews(VERSION)
        self.assertEqual(len(reviews), 1)
        review = reviews[0]
        self.assertEqual(review.reviewer_id, OWNER)
        self.assertEqual(review.authority_reference, f"owner:{OWNER}")
        self.assertEqual(review.decision, "approved")
        self.assertEqual(review.target_owner_id, OWNER)
        self.assertEqual(review.use_scope, ("reference",))
        self.assertEqual(review.evidence_reference, "doi-evidence-1")
        self.assertEqual(review.decided_at, "2026-10-21T00:00:00Z")
        self.assertEqual(review.content_digest, "a" * 64)
        self.assertEqual(review.snapshot_digest, "c" * 64)
        self.assertEqual(review.snapshot_status, "confirmed")
        self.assertEqual(review.unknown_facts, ())

        events = self.store.list_audit_events(VERSION)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "resource_version_review")
        self.assertEqual(events[0].outcome, "approved")
        self.assertEqual(events[0].related_review_id, outcome.review_id)
        self.assertEqual(events[0].actor_id, OWNER)

    def test_delegated_reviewer_with_verified_authority_is_accepted(self) -> None:
        verifier = FakeAuthorizer({("reviewer-2", VERSION, OWNER, "delegation-1")})
        context = AuthorityContext(
            authority_reference="delegation-1", evidence="owner-message-9"
        )

        outcome = self.service(verifier).record_decision(
            VERSION,
            "reviewer-2",
            "approved",
            reason="delegated review",
            evidence="evidence-2",
            scope=("reference",),
            authority_context=context,
        )

        self.assertTrue(outcome.recorded)
        self.assertEqual(verifier.calls, [("reviewer-2", VERSION, OWNER, "delegation-1")])
        self.assertEqual(
            self.store.list_reviews(VERSION)[0].authority_reference, "delegation-1"
        )

    def test_non_owner_without_authority_is_denied_and_stays_pending(self) -> None:
        outcome = self.service().record_decision(
            VERSION, "stranger", "approved", reason="self-asserted"
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "authority_missing")
        self.assertEqual(outcome.qualification.status, "pending")
        self.assertEqual(self.store.list_reviews(VERSION), [])
        events = self.store.list_audit_events(VERSION)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].outcome, "denied")
        self.assertEqual(events[0].reason_code, "authority_missing")
        self.assertIsNone(events[0].related_review_id)

    def test_unverified_authority_is_denied(self) -> None:
        verifier = FakeAuthorizer(set())
        context = AuthorityContext(authority_reference="delegation-x")

        outcome = self.service(verifier).record_decision(
            VERSION,
            "reviewer-2",
            "approved",
            reason="delegated review",
            authority_context=context,
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "authority_unverified")
        self.assertEqual(self.store.list_reviews(VERSION), [])

    def test_authority_without_a_verifier_is_denied(self) -> None:
        outcome = self.service().record_decision(
            VERSION,
            "reviewer-2",
            "approved",
            reason="delegated review",
            authority_context=AuthorityContext(authority_reference="delegation-1"),
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "authority_unverified")

    def test_unknown_owner_cannot_produce_a_decision(self) -> None:
        self.resources.outcome = ResourceVersionRead.confirmed(
            snapshot(owner_id=None)
        )
        verifier = FakeAuthorizer({("reviewer-2", VERSION, "", "delegation-1")})

        outcome = self.service(verifier).record_decision(
            VERSION,
            "reviewer-2",
            "approved",
            reason="delegated review",
            authority_context=AuthorityContext(authority_reference="delegation-1"),
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "owner_unknown")
        self.assertEqual(outcome.qualification.status, "pending")

    def test_absent_exact_version_blocks_approval(self) -> None:
        self.resources.outcome = ResourceVersionRead.missing()

        outcome = self.service().record_decision(
            VERSION, OWNER, "approved", reason="checked"
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "version_missing")
        self.assertEqual(self.store.list_reviews(VERSION), [])
        self.assertEqual(outcome.qualification.status, "pending")

    def test_unreadable_store_blocks_approval(self) -> None:
        self.resources.outcome = ResourceVersionRead.unavailable()

        outcome = self.service().record_decision(
            VERSION, OWNER, "approved", reason="checked"
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "store_unavailable")

    def test_returned_version_must_match_the_requested_id(self) -> None:
        self.resources.outcome = ResourceVersionRead.confirmed(
            snapshot(resource_version_id="rv-2")
        )

        outcome = self.service().record_decision(
            VERSION, OWNER, "approved", reason="checked"
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "version_id_mismatch")
        self.assertEqual(self.store.list_reviews(VERSION), [])

    def test_unknown_facts_and_limitations_are_preserved(self) -> None:
        self.resources.outcome = ResourceVersionRead.confirmed(
            snapshot(
                license=None,
                attribution=None,
                content_digest=None,
                content_checksum_algorithm=None,
                external_version_id=None,
                current_access_locator=None,
                availability_status=None,
                availability_checked_at=None,
                generated_by=None,
                generated_at=None,
            )
        )

        outcome = self.service().record_decision(
            VERSION, OWNER, "approved", reason="metadata-only use"
        )

        self.assertTrue(outcome.recorded)
        review = self.store.list_reviews(VERSION)[0]
        self.assertIn("license", review.unknown_facts)
        self.assertIn("attribution", review.unknown_facts)
        self.assertIn("content_checksum", review.unknown_facts)
        self.assertIn("external_content_unpinned", review.unknown_facts)
        self.assertIn("access_locator", review.unknown_facts)
        self.assertIn("availability_status", review.unknown_facts)
        self.assertIn("generated_by", review.unknown_facts)
        self.assertIn("generated_at", review.unknown_facts)
        self.assertIn("license_unknown", review.limitations)
        self.assertIn("content_unpinned", review.limitations)
        qualification = self.service().get_current_qualification(VERSION)
        self.assertEqual(qualification.status, "approved")
        self.assertIn("license", qualification.unknown_facts)
        self.assertIn("license_unknown", qualification.limitations)

    def test_scope_limits_where_an_approval_applies(self) -> None:
        self.service().record_decision(
            VERSION,
            OWNER,
            "approved",
            reason="metadata-only use",
            scope=("reference",),
        )

        self.assertEqual(
            self.service().get_current_qualification(VERSION, "reference").status,
            "approved",
        )
        self.assertEqual(
            self.service()
            .get_current_qualification(VERSION, "redistribution")
            .status,
            "pending",
        )
        self.assertEqual(
            self.service().get_current_qualification(VERSION).status, "approved"
        )

    def test_rejection_and_reapproval_append_without_overwriting(self) -> None:
        service = self.service()
        first = service.record_decision(VERSION, OWNER, "approved", reason="ok")
        first_review = self.store.list_reviews(VERSION)[0]
        service.record_decision(VERSION, OWNER, "rejected", reason="license changed")
        self.assertEqual(
            service.get_current_qualification(VERSION).status, "rejected"
        )
        service.record_decision(VERSION, OWNER, "approved", reason="reviewed again")

        reviews = self.store.list_reviews(VERSION)
        self.assertEqual(len(reviews), 3)
        self.assertEqual(
            service.get_current_qualification(VERSION).status, "approved"
        )
        self.assertEqual(reviews[0], first_review)
        self.assertEqual(first_review.review_id, first.review_id)
        self.assertEqual(len(self.store.list_audit_events(VERSION)), 3)

    def test_owner_can_revoke_without_a_readable_snapshot(self) -> None:
        service = self.service()
        service.record_decision(
            VERSION, OWNER, "approved", reason="ok", evidence="evidence-1"
        )
        self.resources.outcome = ResourceVersionRead.unavailable()

        outcome = service.record_decision(
            VERSION, OWNER, "revoked", reason="source withdrawn"
        )

        self.assertTrue(outcome.recorded)
        self.assertEqual(outcome.qualification.status, "revoked")
        self.assertEqual(len(self.store.list_reviews(VERSION)), 2)
        review = self.store.list_reviews(VERSION)[-1]
        self.assertEqual(review.snapshot_status, "unavailable")
        self.assertIsNone(review.snapshot_digest)
        self.assertIn("version_unconfirmed", review.unknown_facts)

    def test_unknown_version_cannot_be_revoked_without_any_authority(self) -> None:
        self.resources.outcome = ResourceVersionRead.missing()

        outcome = self.service().record_decision(
            VERSION, "stranger", "revoked", reason="attempt"
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "owner_unknown")

    def test_new_resource_version_does_not_inherit_decisions(self) -> None:
        self.service().record_decision(VERSION, OWNER, "approved", reason="ok")

        qualification = self.service().get_current_qualification("rv-2")

        self.assertEqual(qualification.status, "pending")
        self.assertEqual(qualification.reason_code, "no_effective_decision")

    def test_invalid_decisions_and_missing_evidence_are_rejected(self) -> None:
        service = self.service()
        with self.assertRaises(ValueError):
            service.record_decision(VERSION, OWNER, "accepted", reason="bad word")
        with self.assertRaises(ValueError):
            service.record_decision(VERSION, "", "approved", reason="no actor")
        with self.assertRaises(ValueError):
            service.record_decision(VERSION, OWNER, "approved", reason="")

    def test_every_attempt_reads_the_requested_exact_version(self) -> None:
        self.service().record_decision(VERSION, OWNER, "approved", reason="ok")
        self.assertEqual(self.resources.calls, [(LOCATION, VERSION)])

    def test_missing_location_blocks_approval_without_reading(self) -> None:
        self.locations.location = None

        outcome = self.service().record_decision(
            VERSION, OWNER, "approved", reason="checked"
        )

        self.assertFalse(outcome.recorded)
        self.assertEqual(outcome.reason_code, "exact_version_location_unknown")
        self.assertEqual(outcome.qualification.status, "pending")
        self.assertEqual(self.resources.calls, [])

    def test_recorded_review_keeps_the_exact_location_it_validated(self) -> None:
        self.service().record_decision(VERSION, OWNER, "approved", reason="ok")

        review = self.store.list_reviews(VERSION)[0]

        self.assertEqual(review.target_location, LOCATION)
        self.assertEqual(review.snapshot_status, "confirmed")

    def test_unknown_location_is_not_invented_for_revocation(self) -> None:
        service = self.service()
        service.record_decision(VERSION, OWNER, "approved", reason="ok")
        self.locations.location = None

        outcome = service.record_decision(
            VERSION, OWNER, "revoked", reason="source withdrawn"
        )

        self.assertTrue(outcome.recorded)
        review = self.store.list_reviews(VERSION)[-1]
        self.assertIsNone(review.target_location)
        self.assertEqual(review.snapshot_status, "unavailable")


class SqliteStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(os.path.join(self._tmp.name, "wiki.db"))
        self.store.initialize()

    def test_foreign_keys_are_enabled(self) -> None:
        with self.store.connection() as connection:
            self.assertEqual(
                connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
            )

    def test_initialize_is_idempotent(self) -> None:
        self.store.initialize()
        self.assertEqual(self.store.list_reviews("rv-1"), [])


class ConfigTestCase(unittest.TestCase):
    def test_reads_required_values(self) -> None:
        config = WikiConfig.from_environment(
            {
                "SCIWEAVE_WIKI_SQLITE_PATH": "wiki.db",
                "SCIWEAVE_WIKI_DOMAIN_ID": "wiki-domain",
                "SCIWEAVE_WIKI_TERMINUSDB_URL": "http://127.0.0.1:PORT",
                "SCIWEAVE_WIKI_TERMINUSDB_DATABASE": "wiki-db",
                "SCIWEAVE_WIKI_TERMINUSDB_STORE": "store",
            }
        )
        self.assertEqual(config.sqlite_path, "wiki.db")
        self.assertEqual(config.domain_id, "wiki-domain")
        self.assertIsNone(config.terminusdb_token)

    def test_missing_required_value_raises(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            WikiConfig.from_environment({})
        self.assertIn("SCIWEAVE_WIKI_SQLITE_PATH", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
