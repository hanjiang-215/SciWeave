from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research_mapping.bootstrap import ensure_initial_formal_revision
from research_mapping.domain import SnapshotRead
from research_mapping.sqlite_store import SqliteStore


class InitialFormalRevisionTestCase(unittest.TestCase):
    def test_bootstrap_is_idempotent_and_domain_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "map.sqlite"))
            store.initialize()
            terminus = Mock()
            terminus.ensure_empty_formal_snapshot.return_value = SnapshotRead.confirmed(
                store_id="store", database="map", branch_id="formal-branch", commit_hash="empty-commit", documents=[]
            )
            first = ensure_initial_formal_revision(
                sqlite_store=store, terminus_store=terminus, mapping_domain_id="domain-a"
            )
            second = ensure_initial_formal_revision(
                sqlite_store=store, terminus_store=terminus, mapping_domain_id="domain-a"
            )
            self.assertEqual(first, second)
            terminus.ensure_empty_formal_snapshot.assert_called_once_with("domain-a")
            self.assertEqual(store.get_current_formal_revision_id("domain-a"), first.formal_revision_id)

    def test_unconfirmed_terminus_does_not_write_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "map.sqlite"))
            store.initialize()
            terminus = Mock()
            terminus.ensure_empty_formal_snapshot.return_value = SnapshotRead.unavailable("timeout")
            with self.assertRaisesRegex(RuntimeError, "formal_bootstrap_terminus_unavailable"):
                ensure_initial_formal_revision(
                    sqlite_store=store, terminus_store=terminus, mapping_domain_id="domain-a"
                )
            self.assertIsNone(store.get_current_formal_revision_id("domain-a"))
            with store.connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM formal_mapping_revision").fetchone()[0], 0)

    def test_partial_sqlite_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "map.sqlite"))
            store.initialize()
            with store.connection() as connection:
                connection.execute(
                    "INSERT INTO formal_mapping_revision "
                    "(formal_revision_id,mapping_domain_id,terminus_store_id,formal_branch_id,formal_commit_hash,published_by,published_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("orphan", "domain-a", "store", "branch", "commit", "test", "now"),
                )
                connection.commit()
            with self.assertRaisesRegex(RuntimeError, "formal_bootstrap_partial_state"):
                store.ensure_initial_formal_revision(
                    mapping_domain_id="domain-a", terminus_store_id="store", formal_branch_id="branch",
                    formal_commit_hash="commit", graph_snapshot_digest="digest", published_at="now",
                )


if __name__ == "__main__":
    unittest.main()
