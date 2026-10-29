from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from suitecheck import ManifestError, load_manifest, validate_suite
from suitecheck.validate import errors


BASE = '''\
schema_version: 1
suite: demo
title: Demo suite
version: 1.0.0
role: machine
actor: researcher
summary: Demo suite
boundary:
  may_modify: [project definitions]
  must_not: [secrets]
requires:
  env:
    - name: DEMO_URL
      purpose: Demo service endpoint
      required: true
  services: []
capabilities:
  - name: read
    platforms:
      linux: {status: supported, limitations: []}
      windows: {status: manual, limitations: [manual setup]}
      macos: {status: unverified, limitations: [not tested]}
      other: {status: unsupported, limitations: [not available]}
payloads:
  skills: [{name: demo, path: skills/demo}]
  mcp: []
  hooks: []
  cron: []
  runtime: [{name: worker, path: runtime, role: runtime}]
export:
  harness_input: .sciweave/harness/demo
  include: [suite.yaml, skills]
  exclude: [.env, data]
  configuration: configuration.md
skills:
  - name: demo
    path: skills/demo
mcp: []
hooks: []
cron: []
install: [./install.sh]
check: [./check.sh]
'''


class SchemaV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "suite.yaml").write_text(BASE, encoding="utf-8")
        (self.root / "skills/demo").mkdir(parents=True)
        (self.root / "skills/demo/SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
        (self.root / "runtime").mkdir()
        (self.root / "configuration.md").write_text("# Config\n", encoding="utf-8")

    def replace(self, old: str, new: str) -> None:
        path = self.root / "suite.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_schema_version_is_explicit_and_exposed(self) -> None:
        self.assertEqual(load_manifest(self.root).schema_version, 1)

    def test_unknown_schema_version_is_rejected(self) -> None:
        self.replace("schema_version: 1", "schema_version: 2")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(self.root)
        self.assertEqual(caught.exception.code, "unsupported_schema_version")

    def test_payload_path_escape_is_rejected(self) -> None:
        self.replace("path: skills/demo", "path: ../outside")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(self.root)
        self.assertEqual(caught.exception.code, "invalid_path")

    def test_missing_payload_reference_is_rejected(self) -> None:
        (self.root / "skills/demo/SKILL.md").unlink()
        codes = {finding.code for finding in errors(validate_suite(self.root))}
        self.assertIn("skill_manifest_missing", codes)

    def test_unknown_platform_status_is_rejected(self) -> None:
        self.replace("status: unverified", "status: maybe")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(self.root)
        self.assertEqual(caught.exception.code, "invalid_platform_status")

    def test_platform_capability_cannot_exceed_actor_ceiling(self) -> None:
        self.replace("name: read", "name: formalize")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(self.root)
        self.assertEqual(caught.exception.code, "capability_over_ceiling")

    def test_environment_variable_requires_purpose_and_required_flag(self) -> None:
        self.replace("purpose: Demo service endpoint", "purpose: ''")
        with self.assertRaises(ManifestError):
            load_manifest(self.root)

    def test_runtime_role_is_closed_to_known_values(self) -> None:
        self.replace("role: runtime", "role: unknown")
        with self.assertRaises(ManifestError):
            load_manifest(self.root)


if __name__ == "__main__":
    unittest.main()
