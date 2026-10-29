import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from work_agent_runtime.project_systemd import (
    PURGE_TOKEN,
    ProjectBindingError,
    ProjectBindingStaleError,
    ProjectSystemdManager,
    UninstallConfirmation,
)


def make_project(root: Path) -> Path:
    (root / ".sciweave" / "runtime").mkdir(parents=True)
    (root / ".sciweave" / "data").mkdir()
    (root / ".sciweave" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    return root


class ProjectSystemdManagerTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.config = self.base / "config"

    def manager(self, name: str, *, with_env: bool = True) -> ProjectSystemdManager:
        root = self.base / name
        root.mkdir(parents=True)
        if with_env:
            (root / ".sciweave" / "runtime").mkdir(parents=True)
            (root / ".sciweave" / "data").mkdir()
            (root / ".sciweave" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        return ProjectSystemdManager(root, config_home=self.config)

    # -- paths and unit rendering ---------------------------------------

    def test_paths_are_explicit_and_the_unit_is_project_scoped(self):
        a = self.manager("alpha")
        b = self.manager("beta")
        self.assertEqual(a.runtime_path, a.project_root / ".sciweave" / "runtime")
        self.assertEqual(a.data_path, a.project_root / ".sciweave" / "data")
        self.assertEqual(a.env_path, a.project_root / ".sciweave" / ".env")
        a.generate()
        b.generate()
        self.assertNotEqual(a.unit_name, b.unit_name)
        self.assertIn(a.project_id, a.unit_name)
        self.assertEqual(a.binding_path, a.runtime_path / "project-binding.json")

    def test_unit_escapes_paths_that_contain_spaces(self):
        manager = self.manager("project with spaces")
        unit = manager.generate().read_text(encoding="utf-8")
        escaped = str(manager.runtime_path).replace(" ", "\\x20")
        self.assertIn(f"WorkingDirectory={escaped}", unit)
        self.assertIn("EnvironmentFile=-", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertNotIn(f"WorkingDirectory={manager.runtime_path}", unit, "a raw space would split the value")

    def test_unit_passes_validation_when_systemd_analyze_is_available(self):
        manager = self.manager("verify")
        manager.generate()
        entry = manager.runtime_path / "bin" / "start-subscriber"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text("#!/usr/bin/env sh\nsleep 1\n", encoding="utf-8")
        entry.chmod(0o755)
        unit = manager.generate()
        if not shutil.which("systemd-analyze"):
            self.skipTest("systemd-analyze not installed")
        result = subprocess.run(["systemd-analyze", "verify", str(unit)], capture_output=True, text=True)
        self.assertNotIn("Unknown key", result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_fresh_project_can_be_generated_without_unrelated_files(self):
        manager = self.manager("fresh", with_env=False)
        manager.generate()
        self.assertTrue(manager.binding_path.is_file())
        self.assertTrue(manager.logs_path.is_dir())

    def test_binding_records_every_location_the_instance_owns(self):
        manager = self.manager("bound")
        manager.generate()
        binding = json.loads(manager.binding_path.read_text(encoding="utf-8"))
        self.assertEqual(binding["project_root"], str(manager.project_root))
        self.assertEqual(binding["unit"], manager.unit_name)
        self.assertEqual(binding["data"], str(manager.data_path))

    # -- move / rebind ---------------------------------------------------

    def test_a_moved_project_is_refused_until_explicit_rebind(self):
        manager = self.manager("moving")
        manager.generate()
        moved = self.base / "moved elsewhere"
        manager.project_root.rename(moved)
        with self.assertRaisesRegex(ProjectBindingStaleError, "rebind"):
            manager.start(run_systemctl=False)
        rebound = manager.rebind(moved)
        self.assertEqual(rebound.project_root, moved.resolve())
        self.assertIn(str(moved.resolve()), rebound.binding_path.read_text(encoding="utf-8"))
        rebound.start(run_systemctl=False)

    def test_start_never_infers_the_project_from_the_working_directory(self):
        manager = self.manager("cwd")
        manager.generate()
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.base)
        manager.start(run_systemctl=False)
        self.assertEqual(manager.project_root, (self.base / "cwd").resolve())

    def test_start_refuses_an_instance_that_was_never_generated(self):
        manager = self.manager("unbound")
        with self.assertRaisesRegex(ProjectBindingError, "no project binding"):
            manager.start(run_systemctl=False)

    # -- upgrade ---------------------------------------------------------

    def test_upgrade_keeps_user_definitions_state_and_credentials(self):
        manager = self.manager("upgrading")
        manager.generate()
        sciweave = manager.project_root / ".sciweave"
        (sciweave / "project" / "workflows").mkdir(parents=True)
        (sciweave / "project" / "agent.yaml").write_text("name: mine\n", encoding="utf-8")
        (sciweave / "project" / "workflows" / "wf.yaml").write_text("id: mine\n", encoding="utf-8")
        (sciweave / "data" / "inbox.sqlite3").write_text("db", encoding="utf-8")
        sessions = sciweave / "data" / "sessions"
        sessions.mkdir()
        (sessions / "s1.log").write_text("log", encoding="utf-8")

        manager.upgrade()

        self.assertEqual((sciweave / "project" / "agent.yaml").read_text(encoding="utf-8"), "name: mine\n")
        self.assertEqual((sciweave / "project" / "workflows" / "wf.yaml").read_text(encoding="utf-8"), "id: mine\n")
        self.assertEqual((sciweave / "data" / "inbox.sqlite3").read_text(encoding="utf-8"), "db")
        self.assertEqual((sessions / "s1.log").read_text(encoding="utf-8"), "log")
        self.assertEqual((sciweave / ".env").read_text(encoding="utf-8"), "TOKEN=secret\n")

    def test_upgrade_validates_the_manifest_before_replacing_anything(self):
        manager = self.manager("guarded")
        manager.generate()
        unit_before = manager.unit_path.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ProjectBindingError, "manifest validation failed"):
            manager.upgrade(manifest=self.base / "absent-suite.yaml")
        self.assertEqual(manager.unit_path.read_text(encoding="utf-8"), unit_before)

    def test_upgrade_refuses_a_stale_binding(self):
        manager = self.manager("stale")
        manager.generate()
        binding = json.loads(manager.binding_path.read_text(encoding="utf-8"))
        binding["project_root"] = str(self.base / "somewhere-else")
        manager.binding_path.write_text(json.dumps(binding), encoding="utf-8")
        with self.assertRaises(ProjectBindingStaleError):
            manager.upgrade()

    # -- uninstall -------------------------------------------------------

    def test_uninstall_keeps_data_project_and_env(self):
        manager = self.manager("removing")
        manager.generate()
        sciweave = manager.project_root / ".sciweave"
        (sciweave / "project").mkdir(parents=True, exist_ok=True)
        (sciweave / "project" / "keep.yaml").write_text("keep\n", encoding="utf-8")
        (sciweave / "data" / "state.db").write_text("state", encoding="utf-8")

        manager.uninstall(run_systemctl=False)

        self.assertTrue((sciweave / "data" / "state.db").is_file())
        self.assertTrue((sciweave / "project" / "keep.yaml").is_file())
        self.assertTrue((sciweave / ".env").is_file())
        self.assertFalse(manager.unit_path.exists())
        self.assertFalse(manager.runtime_path.exists(), "runtime code is removed by default")

    def test_uninstall_requires_an_explicit_token_to_purge_data(self):
        manager = self.manager("purging")
        manager.generate()
        (manager.data_path / "state.db").write_text("state", encoding="utf-8")
        with self.assertRaisesRegex(ProjectBindingError, "confirmation token"):
            manager.uninstall(UninstallConfirmation(purge_data=True), run_systemctl=False)
        self.assertTrue((manager.data_path / "state.db").is_file())
        manager.uninstall(UninstallConfirmation(purge_data=True, token=PURGE_TOKEN), run_systemctl=False)
        self.assertFalse(manager.data_path.exists())
        self.assertTrue(manager.env_path.is_file(), ".env survives a data purge")

    # -- legacy ----------------------------------------------------------

    def test_legacy_states_are_reported_not_guessed(self):
        legacy = self.base / "legacy"
        legacy.mkdir()
        self.assertEqual(ProjectSystemdManager.inspect_legacy(legacy).status, "unbound")
        self.assertEqual(ProjectSystemdManager.inspect_legacy(self.base / "absent").status, "missing")

        (legacy / "project-binding.json").write_text(json.dumps({"project_root": str(self.base / "gone")}), encoding="utf-8")
        stale = ProjectSystemdManager.inspect_legacy(legacy)
        self.assertEqual(stale.status, "stale")
        self.assertEqual(stale.bound_project, (self.base / "gone").resolve())

        (legacy / "project-binding.json").write_text("not json", encoding="utf-8")
        self.assertEqual(ProjectSystemdManager.inspect_legacy(legacy).status, "ambiguous")

    def test_legacy_migration_needs_both_an_explicit_target_and_a_binding(self):
        legacy = self.base / "legacy"
        legacy.mkdir()
        target = make_project(self.base / "target")
        with self.assertRaisesRegex(ProjectBindingError, "ownership is unknown"):
            ProjectSystemdManager.migrate_legacy(legacy, target, config_home=self.config)

        (legacy / "project-binding.json").write_text(json.dumps({"project_root": str(target)}), encoding="utf-8")
        manager = ProjectSystemdManager.migrate_legacy(legacy, target, config_home=self.config)
        self.assertEqual(json.loads(manager.binding_path.read_text(encoding="utf-8"))["project_root"], str(target.resolve()))

    def test_legacy_description_honours_config_home(self):
        legacy = self.base / "legacy"
        legacy.mkdir()
        (legacy / "some-state").mkdir()
        described = ProjectSystemdManager.describe_legacy(legacy, config_home=self.config)
        self.assertEqual(described["status"], "unbound")
        self.assertIn("some-state", described["entries"])
        self.assertEqual(described["unit_files"], [])


if __name__ == "__main__":
    unittest.main()
