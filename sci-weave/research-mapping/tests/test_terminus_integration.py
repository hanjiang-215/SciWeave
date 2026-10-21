from __future__ import annotations

import os
import unittest

from research_mapping.terminus_store import TerminusDBStore

REQUIRED_VARIABLES = (
    "SCIWEAVE_MAPPING_TERMINUSDB_URL",
    "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
)


class TerminusDBExactCommitIntegrationTestCase(unittest.TestCase):
    """Opt-in check against the pinned TerminusDB 12.0.8 service.

    A skipped run is not evidence: set ``SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1``,
    prepare the database, and provide an existing commit hash.
    """

    def setUp(self) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 "
                "and start the pinned TerminusDB service"
            )
        missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
        if missing:
            self.fail("integration configuration missing: " + ", ".join(missing))
        self.base_url = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_URL"]
        self.database = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_DATABASE"]
        self.store = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_STORE"]
        self.branch = os.environ.get("SCIWEAVE_MAPPING_INTEGRATION_BRANCH", "main")
        self.commit = os.environ.get("SCIWEAVE_MAPPING_INTEGRATION_COMMIT")
        self.head_commit = os.environ.get("SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT")
        self.adapter = TerminusDBStore(
            base_url=self.base_url,
            token=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN"),
            username=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD"),
            remote=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_REMOTE", "local"),
        )

    def test_reads_the_exact_commit_instead_of_the_branch_head(self) -> None:
        if not self.commit:
            self.fail(
                "SCIWEAVE_MAPPING_INTEGRATION_COMMIT must name an existing commit"
            )

        outcome = self.adapter.read_exact_snapshot(
            self.store, self.database, self.branch, self.commit
        )

        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)
        self.assertEqual(outcome.store_id, self.store)
        self.assertEqual(outcome.database, self.database)
        self.assertEqual(outcome.branch_id, self.branch)
        self.assertEqual(outcome.commit_hash, self.commit)
        self.assertTrue(outcome.content_digest)

    def test_historical_commit_differs_from_the_branch_head(self) -> None:
        if not self.commit or not self.head_commit:
            self.skipTest(
                "set SCIWEAVE_MAPPING_INTEGRATION_COMMIT and "
                "SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT to compare snapshots"
            )
        if self.commit == self.head_commit:
            self.fail("historical commit must differ from the branch head commit")

        historical = self.adapter.read_exact_snapshot(
            self.store, self.database, self.branch, self.commit
        )
        head = self.adapter.read_exact_snapshot(
            self.store, self.database, self.branch, self.head_commit
        )

        self.assertEqual(historical.status, "confirmed", historical.reason_code)
        self.assertEqual(head.status, "confirmed", head.reason_code)
        self.assertNotEqual(
            tuple(document.get("@id") for document in historical.documents),
            tuple(document.get("@id") for document in head.documents),
        )

    def test_unknown_commit_is_never_confirmed(self) -> None:
        # Measured on the pinned container: an unknown commit hash is answered
        # with HTTP 500 ``api:InternalServerError`` for both the document and
        # the log route, never 404. A server fault cannot prove absence, so the
        # adapter must report ``unavailable`` and never a confirmed snapshot.
        outcome = self.adapter.read_exact_snapshot(
            self.store,
            self.database,
            self.branch,
            "0000000000000000000000000000000000000000",
        )

        self.assertEqual(outcome.status, "unavailable", outcome.reason_code)
        self.assertEqual(outcome.reason_code, "store_unavailable")
        self.assertEqual(outcome.documents, ())


if __name__ == "__main__":
    unittest.main()
