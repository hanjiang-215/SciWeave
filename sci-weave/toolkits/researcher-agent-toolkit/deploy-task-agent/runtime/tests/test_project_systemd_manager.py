import shutil
import subprocess
import unittest
from pathlib import Path

from work_agent_runtime.project_systemd import (
    ProjectBindingError,
    ProjectBindingStaleError,
    ProjectSystemdManager,
    UninstallConfirmation,
)


def make_project(tmp_path: Path, name: str = "project with spaces") -> Path:
    root = tmp_path / name
    (root / ".sciweave" / "runtime").mkdir(parents=True)
    (root / ".sciweave" / "data").mkdir()
    (root / ".sciweave" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    return root


class ProjectSystemdManagerTests(unittest.TestCase):
    def test_binding_is_project_specific_and_paths_are_explicit(self):
        with self.subTest("paths"):
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                root = make_project(Path(directory))
                manager = ProjectSystemdManager(root, config_home=Path(directory) / "config")
                self.assertEqual(manager.project_root, root.resolve())
                self.assertEqual(manager.project_id, ProjectSystemdManager(root, config_home=Path(directory) / "other").project_id)
                self.assertEqual(manager.runtime_path, root / ".sciweave" / "runtime")
                self.assertEqual(manager.data_path, root / ".sciweave" / "data")
                self.assertEqual(manager.env_path, root / ".sciweave" / ".env")
                self.assertIn("task-agent-", manager.unit_name)

    def test_generate_writes_space_safe_unit_and_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = make_project(Path(directory))
            manager = ProjectSystemdManager(root, config_home=Path(directory) / "config")
            unit = manager.generate()
            text = unit.read_text(encoding="utf-8")
            self.assertIn(f'WorkingDirectory="{root / ".sciweave" / "runtime"}"', text)
            self.assertIn(f'EnvironmentFile="{root / ".sciweave" / ".env"}"', text)
            self.assertTrue(manager.binding_path.exists())
            self.assertIn(str(root.resolve()), manager.binding_path.read_text(encoding="utf-8"))
            if shutil.which("systemd-analyze"):
                result = subprocess.run(["systemd-analyze", "verify", str(unit)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 2, result.stderr)

    def test_legacy_migration_requires_explicit_target_and_binding(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy = base / "legacy"
            legacy.mkdir()
            target = make_project(base, "target")
            with self.assertRaisesRegex(ProjectBindingError, "ownership is unknown"):
                ProjectSystemdManager.migrate_legacy(legacy, target, config_home=base / "config")
            import json
            (legacy / "project-binding.json").write_text(
                json.dumps({"project_root": str(target)}), encoding="utf-8"
            )
            manager = ProjectSystemdManager.migrate_legacy(legacy, target, config_home=base / "config")
            self.assertTrue(manager.binding_path.exists())

    def test_uninstall_keeps_data_env_and_project_by_default(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = make_project(base)
            (root / ".sciweave" / "data" / "state.db").write_text("state", encoding="utf-8")
            manager = ProjectSystemdManager(root, config_home=base / "config")
            manager.generate()
            manager.uninstall()
            self.assertTrue(manager.data_path.joinpath("state.db").exists())
            self.assertTrue(manager.env_path.exists())
            self.assertFalse(manager.unit_path.exists())

    def test_uninstall_purge_requires_explicit_confirmation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = make_project(Path(directory))
            manager = ProjectSystemdManager(root, config_home=Path(directory) / "config")
            with self.assertRaisesRegex(ProjectBindingError, "confirmation token"):
                manager.uninstall(UninstallConfirmation(purge_data=True))

    def test_start_rejects_moved_project_until_explicit_rebind(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = make_project(base)
            config = base / "config"
            manager = ProjectSystemdManager(root, config_home=config)
            manager.generate()
            moved = base / "moved project"
            root.rename(moved)
            with self.assertRaisesRegex(ProjectBindingStaleError, "rebind"):
                manager.start(run_systemctl=False)
            rebound = manager.rebind(moved)
            self.assertEqual(rebound.project_root, moved.resolve())
            self.assertIn(str(moved.resolve()), rebound.binding_path.read_text(encoding="utf-8"))
            rebound.start(run_systemctl=False)


if __name__ == "__main__":
    unittest.main()
