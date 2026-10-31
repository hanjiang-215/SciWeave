"""Tests for the suite manifest and its validator.

Fixtures are built in a temporary directory rather than checked in: the point
is that a *minimal* suite passes and each single defect is caught, and a
checked-in fixture would drift into "whatever the real suites happen to look
like".
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from suitecheck import (
    ManifestError,
    ROLE_CAPABILITIES,
    SuiteManifest,
    find_suites,
    load_manifest,
    validate_suite,
)
from suitecheck.cli import main as cli_main
from suitecheck.validate import duplicate_skills, errors


def _write_skill(root: Path, suite: str, name: str, path: str = "") -> str:
    relative = path or f"skills/{name}"
    directory = root / relative
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {suite}-{name}\ndescription: does {name}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return relative


def _write_card(root: Path, name: str, *, capabilities: tuple[str, ...] = (), tools: tuple[str, ...] = ("do_it",)) -> str:
    path = f"mcp/{name}/mcp.json"
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "name": name,
                "transport": "streamable-http",
                "endpoint": {"url_env": f"{name.upper().replace('-', '_')}_MCP_URL"},
                "tools": [{"name": tool} for tool in tools],
                "capabilities": list(capabilities),
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_hook(root: Path, name: str) -> str:
    path = f"hooks/{name}.sh"
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return path


MINIMAL = """\
suite: demo-suite
role: machine
actor: researcher
title: Demo suite
version: 0.1.0
summary: >
  A suite used only by the tests. It declares one skill, one card, one hook and
  the two commands every suite needs.
boundary:
  may_modify: [agent definitions]
  must_not: [formal revisions]
requires:
  env: [DEMO_MCP_URL]
  services: []
skills:
  - name: alpha
    path: {skill_path}
mcp:
  - name: demo-domain
    card: {card_path}
    capabilities: [read, candidate_submit]
hooks:
  - name: check
    path: {hook_path}
    event: harness-open
cron:
  - name: heartbeat
    path: cron/heartbeat.sh
    schedule: "*/5 * * * *"
install:
  - ./install.sh
check:
  - ./check.sh
"""


class SuiteFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

    def build(self, **overrides: str) -> Path:
        skill_path = _write_skill(self.root, "demo-suite", "alpha")
        card_path = _write_card(self.root, "demo-domain", capabilities=("read", "candidate_submit"))
        hook_path = _write_hook(self.root, "check")
        cron = self.root / "cron/heartbeat.sh"
        cron.parent.mkdir(parents=True, exist_ok=True)
        cron.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        fields = {
            "skill_path": skill_path,
            "card_path": card_path,
            "hook_path": hook_path,
        }
        fields.update(overrides)
        (self.root / "suite.yaml").write_text(MINIMAL.format(**fields), encoding="utf-8")
        return self.root


class ManifestTests(SuiteFixture):
    def test_a_minimal_suite_validates_cleanly(self) -> None:
        suite = load_manifest(self.build())
        self.assertEqual(suite.suite, "demo-suite")
        self.assertEqual(suite.effective_actor, "researcher")
        self.assertEqual(validate_suite(suite), [])

    def test_an_unknown_key_is_an_error_not_a_comment(self) -> None:
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace(
            "check:\n  - ./check.sh\n", "check:\n  - ./check.sh\nnotes: hello\n"
        )
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(root)
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_a_missing_required_key_names_itself(self) -> None:
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace("version: 0.1.0\n", "")
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(root)
        self.assertEqual(caught.exception.code, "missing_version")

    def test_an_unknown_role_is_rejected(self) -> None:
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace("role: machine", "role: robot")
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(root)
        self.assertEqual(caught.exception.code, "invalid_role")

    def test_a_human_suite_cannot_act_as_a_machine(self) -> None:
        root = self.build()
        text = (
            (root / "suite.yaml")
            .read_text(encoding="utf-8")
            .replace("role: machine", "role: human")
            .replace("actor: researcher", "actor: machine")
        )
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        with self.assertRaises(ManifestError) as caught:
            load_manifest(root)
        self.assertEqual(caught.exception.code, "role_actor_mismatch")

    def test_a_machine_suite_defaults_to_the_researcher_ceiling(self) -> None:
        """`role` says where it installs; the actor decides what it may call."""
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace("actor: researcher\n", "")
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        suite = load_manifest(root)
        self.assertEqual(suite.effective_actor, "researcher")
        self.assertEqual(suite.capability_ceiling, ROLE_CAPABILITIES["researcher"])

    def test_the_centre_ceiling_excludes_formalize(self) -> None:
        self.assertNotIn("formalize", ROLE_CAPABILITIES["centre"])

    def test_the_project_owner_ceiling_excludes_centre(self) -> None:
        self.assertNotIn("centre", ROLE_CAPABILITIES["project_owner"])

    def test_a_machine_ceiling_is_read_only(self) -> None:
        self.assertEqual(ROLE_CAPABILITIES["machine"], frozenset({"read"}))


class PayloadTests(SuiteFixture):
    def test_a_missing_skill_manifest_is_an_error(self) -> None:
        root = self.build()
        (root / "skills/alpha/SKILL.md").unlink()
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("skill_manifest_missing", codes)

    def test_a_skill_without_frontmatter_is_an_error(self) -> None:
        root = self.build()
        (root / "skills/alpha/SKILL.md").write_text("# alpha\n", encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("skill_frontmatter_missing", codes)

    def test_two_skills_may_not_share_a_frontmatter_name(self) -> None:
        root = self.build()
        second = _write_skill(root, "demo-suite", "beta")
        (root / "skills/beta/SKILL.md").write_text(
            "---\nname: demo-suite-alpha\ndescription: same name as alpha\n---\n", encoding="utf-8"
        )
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace(
            "mcp:\n", f"  - name: beta\n    path: {second}\nmcp:\n"
        )
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("skill_name_duplicate", codes)

    def test_a_card_naming_another_server_is_an_error(self) -> None:
        root = self.build()
        card = json.loads((root / "mcp/demo-domain/mcp.json").read_text(encoding="utf-8"))
        card["name"] = "something-else"
        (root / "mcp/demo-domain/mcp.json").write_text(json.dumps(card), encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("mcp_name_mismatch", codes)

    def test_a_remote_card_must_name_its_url_variable(self) -> None:
        root = self.build()
        card = json.loads((root / "mcp/demo-domain/mcp.json").read_text(encoding="utf-8"))
        card.pop("endpoint")
        (root / "mcp/demo-domain/mcp.json").write_text(json.dumps(card), encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("mcp_card_incomplete", codes)

    def test_a_capability_above_the_ceiling_is_refused(self) -> None:
        """The whole reason the ceiling exists: a card cannot hand itself more."""
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace(
            "capabilities: [read, candidate_submit]", "capabilities: [read, formalize]"
        )
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("capability_over_ceiling", codes)

    def test_an_unknown_capability_is_refused(self) -> None:
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace(
            "capabilities: [read, candidate_submit]", "capabilities: [read, superuser]"
        )
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("capability_unknown", codes)

    @unittest.skipUnless(os.name == "posix", "a POSIX executable bit cannot be removed (or observed) on Windows")
    def test_a_hook_must_be_executable(self) -> None:
        root = self.build()
        hook = root / "hooks/check.sh"
        hook.chmod(hook.stat().st_mode & ~stat.S_IXUSR)
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("hook_not_executable", codes)

    def test_a_declared_hook_file_must_exist(self) -> None:
        root = self.build()
        (root / "hooks/check.sh").unlink()
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("hook_missing", codes)

    def test_an_empty_boundary_is_an_error(self) -> None:
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace(
            "  may_modify: [agent definitions]\n", "  may_modify: []\n"
        )
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("boundary_missing", codes)

    def test_a_declared_env_var_set_in_this_shell_is_flagged(self) -> None:
        """The secret-boundary warning must fire on a real declared env name."""
        root = self.build()
        import os

        os.environ["DEMO_MCP_URL"] = "https://user:pass@example.test"
        self.addCleanup(os.environ.pop, "DEMO_MCP_URL", None)
        findings = validate_suite(root)
        codes = {finding.code for finding in findings}
        self.assertIn("env_looks_like_secret", codes)

    def test_a_suite_may_declare_no_commands(self) -> None:
        """Spec §6 retires install/check as an execution contract: absence is legal."""
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8")
        text = text.replace("install:\n  - ./install.sh\n", "").replace("check:\n  - ./check.sh\n", "")
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertNotIn("install_commands_missing", codes)
        self.assertNotIn("check_commands_missing", codes)

    def test_a_suite_without_payload_is_empty(self) -> None:
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8")
        text = text.split("skills:")[0] + "install:\n  - ./install.sh\ncheck:\n  - ./check.sh\n"
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertIn("suite_empty", codes)

    def test_a_suite_may_declare_skills_and_no_cards(self) -> None:
        # ai4-349h / ai4-0wg0: a suite that only installs configuration for a
        # service talks to MCP servers whose cards belong to that service's
        # source, not to the suite tree. Declaring no cards is a real shape;
        # declaring nothing is not.
        root = self.build()
        text = (root / "suite.yaml").read_text(encoding="utf-8")
        start = text.index("mcp:")
        end = text.index("hooks:")
        (root / "suite.yaml").write_text(text[:start] + text[end:], encoding="utf-8")
        codes = {finding.code for finding in errors(validate_suite(root))}
        self.assertEqual(codes, set())


class CrossSuiteTests(SuiteFixture):
    def _suite(self, parent: Path, suite: str, skill_name: str) -> SuiteManifest:
        root = parent / suite
        _write_skill(root, suite, "alpha")
        (root / "skills/alpha/SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: shared\n---\n", encoding="utf-8"
        )
        _write_card(root, "demo-domain")
        _write_hook(root, "check")
        (root / "suite.yaml").write_text(
            MINIMAL.format(
                skill_path="skills/alpha",
                card_path="mcp/demo-domain/mcp.json",
                hook_path="hooks/check.sh",
            )
            .replace("suite: demo-suite", f"suite: {suite}")
            .replace("cron:\n  - name: heartbeat\n    path: cron/heartbeat.sh\n    schedule: \"*/5 * * * *\"\n", ""),
            encoding="utf-8",
        )
        return load_manifest(root)

    def test_one_skill_name_in_two_suites_is_an_error(self) -> None:
        """The failure this check exists for: two suites in one harness."""
        first = self._suite(self.root, "first-suite", "shared-skill")
        second = self._suite(self.root, "second-suite", "shared-skill")
        findings = duplicate_skills([first, second])
        self.assertEqual([finding.code for finding in findings], ["skill_name_shared_between_suites"])

    def test_distinct_skill_names_across_suites_are_fine(self) -> None:
        first = self._suite(self.root, "first-suite", "first-skill")
        second = self._suite(self.root, "second-suite", "second-skill")
        self.assertEqual(duplicate_skills([first, second]), [])


class DiscoveryTests(SuiteFixture):
    def test_find_suites_returns_the_directory_not_the_file(self) -> None:
        root = self.build()
        found = find_suites(root.parent)
        self.assertEqual(found, [root])


class CliTests(SuiteFixture):
    def test_check_exits_zero_on_a_clean_suite(self) -> None:
        root = self.build()
        self.assertEqual(cli_main(["check", str(root)]), 0)

    def test_check_exits_one_on_an_error(self) -> None:
        root = self.build()
        (root / "skills/alpha/SKILL.md").unlink()
        self.assertEqual(cli_main(["check", str(root)]), 1)

    def test_run_lists_commands_without_running_them(self) -> None:
        root = self.build()
        marker = root / "ran"
        (root / "install.sh").write_text(f"#!/usr/bin/env sh\ntouch {marker}\n", encoding="utf-8")
        (root / "install.sh").chmod(0o755)
        text = (root / "suite.yaml").read_text(encoding="utf-8").replace("./install.sh", "./install.sh")
        (root / "suite.yaml").write_text(text, encoding="utf-8")
        self.assertEqual(cli_main(["run", "install", str(root)]), 0)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
