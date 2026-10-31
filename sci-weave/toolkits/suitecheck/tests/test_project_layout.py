from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from suitecheck.project_layout import ProjectRootRequired, initialize_project


class ProjectLayoutTests(unittest.TestCase):
    def test_initializes_isolated_project_tree_and_classified_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = initialize_project(root)
            self.assertEqual(layout.root, root.resolve())
            for relative in (
                ".sciweave/harness",
                ".sciweave/runtime",
                ".sciweave/data",
                ".sciweave/project",
            ):
                self.assertTrue((root / relative).is_dir())
            text = (root / ".sciweave/.gitignore").read_text(encoding="utf-8")
            self.assertIn("/data/", text)
            self.assertIn("/.env", text)
            self.assertIn("!/project/", text)
            self.assertIn("!/project/**/*.yaml", text)
            self.assertNotIn("\n*\n", text)

    def test_initialization_is_idempotent_and_preserves_custom_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_project(root)
            custom = root / ".sciweave/project/agent.yaml"
            custom.write_text("name: local\n", encoding="utf-8")
            initialize_project(root)
            self.assertEqual(custom.read_text(encoding="utf-8"), "name: local\n")

    def test_missing_project_root_is_explicitly_rejected(self) -> None:
        with self.assertRaises(ProjectRootRequired):
            initialize_project(None)


if __name__ == "__main__":
    unittest.main()
