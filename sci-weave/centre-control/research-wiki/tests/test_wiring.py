"""Wiring contract for the Wiki production entry point (ai4-n7js).

The candidate -> review -> formalize chain needs the *candidate* store. The
entry point used to build the read-only resource store, and because every
missing capability is reported as a result code instead of an exception, the
three write tools failed silently in production while the suites stayed green.
These tests pin the interface difference and the wiring itself.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from llm_wiki.terminus_store import TerminusDBResourceStore, TerminusDBWikiCandidateStore

_WRITE_SURFACE = (
    "create_candidate_snapshot",
    "read_branch_head",
    "create_formal_snapshot",
    "verify_formalization_commit",
)

_MAIN = Path(__file__).resolve().parents[1] / "src" / "main.py"


class CandidateStoreSurfaceTests(unittest.TestCase):
    def test_candidate_store_provides_the_write_surface(self) -> None:
        for name in _WRITE_SURFACE:
            self.assertTrue(
                callable(getattr(TerminusDBWikiCandidateStore, name, None)),
                f"candidate store is missing {name}",
            )

    def test_read_only_store_cannot_serve_the_write_surface(self) -> None:
        """This is why the old wiring could never create or formalize anything."""
        for name in _WRITE_SURFACE:
            self.assertFalse(
                hasattr(TerminusDBResourceStore, name),
                f"read-only store unexpectedly grew {name}; revisit the entry point",
            )


class EntryPointWiringTests(unittest.TestCase):
    def test_entry_point_builds_the_candidate_store(self) -> None:
        source = _MAIN.read_text(encoding="utf-8")
        self.assertIn("TerminusDBWikiCandidateStore(", source)
        self.assertNotIn("TerminusDBResourceStore(", source)

    def test_entry_point_passes_the_store_and_database(self) -> None:
        source = _MAIN.read_text(encoding="utf-8")
        self.assertIn("store_id=config.terminusdb_store", source)
        self.assertIn("database=config.terminusdb_database", source)


if __name__ == "__main__":
    unittest.main()
