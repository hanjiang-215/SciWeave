from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from suitecheck.exporter import ExportError, export_suite
from suitecheck.project_layout import ProjectRootRequired


class ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.suite = Path(self._temp.name) / "suite"
        self.project = Path(self._temp.name) / "project with spaces"
        (self.suite / "skills" / "alpha").mkdir(parents=True)
        (self.suite / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: demo\n---\n", encoding="utf-8"
        )
        (self.suite / "mcp" / "demo").mkdir(parents=True)
        (self.suite / "mcp" / "demo" / "mcp.json").write_text('{"name":"demo"}\n', encoding="utf-8")
        (self.suite / "configuration.md").write_text(
            "# Config\n\nSet `DEMO_TOKEN` in the project environment. Example: DEMO_TOKEN=<your-token>\n",
            encoding="utf-8",
        )
        (self.suite / ".env").write_text("DEMO_TOKEN=super-secret-value\n", encoding="utf-8")
        (self.suite / "suite.yaml").write_text(
            """\
schema_version: 1
suite: demo-suite
role: human
actor: project_owner
title: Demo
version: 0.1.0
summary: Demo export
boundary:
  may_modify: [decisions]
  must_not: [secrets]
requires:
  env:
    - name: DEMO_TOKEN
      purpose: demo credential
      required: true
  services: []
capabilities:
  - name: read
    platforms:
      linux: {status: supported, limitations: []}
      windows: {status: manual, limitations: [manual registration]}
export:
  harness_input: .sciweave/harness/demo-suite
  include: [suite.yaml, skills, mcp, configuration.md]
  exclude: [.env, data]
  configuration: configuration.md
skills:
  - name: alpha
    path: skills/alpha
mcp:
  - name: demo
    card: mcp/demo/mcp.json
    capabilities: [read]
hooks: []
cron: []
install: []
check: []
""",
            encoding="utf-8",
        )

    def test_export_requires_explicit_project_root(self) -> None:
        with self.assertRaises(ProjectRootRequired):
            export_suite(self.suite, None)
        with self.assertRaises(ProjectRootRequired):
            export_suite(self.suite, "   ")

    def test_export_is_self_contained_and_secret_free(self) -> None:
        result = export_suite(self.suite, self.project)
        output = result.output_dir
        self.assertEqual(output, (self.project / ".sciweave" / "harness" / "demo-suite").resolve())
        self.assertTrue((output / "skills" / "alpha" / "SKILL.md").is_file())
        self.assertTrue((output / "mcp" / "demo" / "mcp.json").is_file())
        self.assertFalse((output / ".env").exists())
        text = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file())
        self.assertNotIn("super-secret-value", text)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["suite"], "demo-suite")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["actor"], "project_owner")
        self.assertIn("skills", manifest["inputs"])
        self.assertEqual(manifest["environment"][0]["name"], "DEMO_TOKEN")
        self.assertEqual(manifest["capabilities"][0]["platforms"]["windows"]["status"], "manual")

    def test_a_secret_in_a_published_file_is_refused(self) -> None:
        (self.suite / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: demo\n---\nDEMO_TOKEN=abc123realtoken\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ExportError, "secret value"):
            export_suite(self.suite, self.project)
        self.assertFalse((self.project / ".sciweave" / "harness" / "demo-suite").exists())

    def test_placeholder_guidance_is_not_a_secret(self) -> None:
        (self.suite / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: demo\n---\n"
            "DEMO_TOKEN=<your-token>\nOTHER_TOKEN=${DEMO_TOKEN}\nTHIRD_TOKEN=\n",
            encoding="utf-8",
        )
        result = export_suite(self.suite, self.project)
        self.assertTrue(result.manifest_path.is_file())

    def test_a_prose_constant_is_not_a_secret(self) -> None:
        """A confirmation phrase in source code is not a credential."""
        (self.suite / "skills" / "alpha" / "purge.py").write_text(
            'PURGE_TOKEN = "PURGE SCIWEAVE DATA"\n', encoding="utf-8"
        )
        result = export_suite(self.suite, self.project)
        self.assertTrue(result.manifest_path.is_file())

    def test_repeat_export_preserves_project_data_and_env(self) -> None:
        export_suite(self.suite, self.project)
        sciweave = self.project / ".sciweave"
        (sciweave / "project").mkdir(parents=True, exist_ok=True)
        custom = sciweave / "project" / "agent.yaml"
        custom.write_text("name: local\n", encoding="utf-8")
        (sciweave / "data").mkdir(exist_ok=True)
        (sciweave / "data" / "state.db").write_text("state", encoding="utf-8")
        (sciweave / ".env").write_text("KEEP=1\n", encoding="utf-8")
        stale = sciweave / "harness" / "demo-suite" / "user-note.txt"
        stale.write_text("keep-me\n", encoding="utf-8")
        export_suite(self.suite, self.project)
        self.assertEqual(custom.read_text(encoding="utf-8"), "name: local\n")
        self.assertEqual((sciweave / "data" / "state.db").read_text(encoding="utf-8"), "state")
        self.assertEqual((sciweave / ".env").read_text(encoding="utf-8"), "KEEP=1\n")
        self.assertFalse(stale.exists(), "generated directory must be refreshed, not merged")

    def test_interrupted_refresh_is_recovered_on_the_next_run(self) -> None:
        export_suite(self.suite, self.project)
        harness = self.project / ".sciweave" / "harness"
        output = harness / "demo-suite"
        output.rename(harness / ".demo-suite.previous")
        export_suite(self.suite, self.project)
        self.assertTrue((output / "manifest.json").is_file())
        self.assertFalse((harness / ".demo-suite.previous").exists())

    def test_path_escape_is_rejected(self) -> None:
        text = (self.suite / "suite.yaml").read_text(encoding="utf-8").replace("skills/alpha", "../outside")
        (self.suite / "suite.yaml").write_text(text, encoding="utf-8")
        with self.assertRaises(ExportError):
            export_suite(self.suite, self.project)


if __name__ == "__main__":
    unittest.main()
