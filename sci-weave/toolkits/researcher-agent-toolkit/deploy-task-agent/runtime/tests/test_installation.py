"""The kit has to be installable, not only importable (ai4-8aa0).

These tests cover the wiring that no unit test touched before: the systemd
units point at scripts that must exist, the start scripts must resolve the kit
from their own location, and the harness hook must not fail on a machine where
the kit was never installed.
"""

import os
import re
import subprocess
import unittest
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[2]
UNITS = KIT_ROOT / "systemd"
BIN = KIT_ROOT / "bin"


class SystemdUnitTests(unittest.TestCase):
    def _units(self) -> list[Path]:
        return sorted(UNITS.glob("*.service"))

    def test_both_roles_have_a_unit(self) -> None:
        self.assertEqual(
            {path.name for path in self._units()},
            {"sciweave-task-agent-mcp.service", "sciweave-task-agent-subscriber.service"},
        )

    def test_every_exec_start_points_at_a_script_in_the_kit(self) -> None:
        """The units used to reference `bin/start-*`, which never existed."""
        for path in self._units():
            with self.subTest(unit=path.name):
                text = path.read_text(encoding="utf-8")
                match = re.search(r"^ExecStart=(.+)$", text, re.MULTILINE)
                self.assertIsNotNone(match, "ExecStart is required")
                executable = match.group(1).replace("%h/.sciweave/task-agent", str(KIT_ROOT)).strip()
                self.assertTrue(Path(executable).is_file(), f"{path.name} runs a missing file: {executable}")
                self.assertTrue(os.access(executable, os.X_OK), f"{path.name} runs a non-executable: {executable}")

    def test_every_unit_has_a_working_directory_and_env_file(self) -> None:
        for path in self._units():
            with self.subTest(unit=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("WorkingDirectory=%h/.sciweave/task-agent", text)
                self.assertIn("EnvironmentFile=%h/.sciweave/task-agent/.env", text)


class StartScriptTests(unittest.TestCase):
    def test_start_scripts_exist_and_are_executable(self) -> None:
        for name in ("start-mcp", "start-subscriber"):
            with self.subTest(name=name):
                path = BIN / name
                self.assertTrue(path.is_file(), f"{name} is missing")
                self.assertTrue(os.access(path, os.X_OK), f"{name} is not executable")

    def test_start_scripts_resolve_the_kit_from_their_own_location(self) -> None:
        """Hardcoding ~/.sciweave would break SCIWEAVE_TASK_AGENT_HOME."""
        for name in ("start-mcp", "start-subscriber"):
            with self.subTest(name=name):
                text = (BIN / name).read_text(encoding="utf-8")
                self.assertIn('dirname -- "$0"', text)
                self.assertNotIn("~/.sciweave", text)

    def test_start_scripts_fail_fast_without_an_env_file(self) -> None:
        text = (BIN / "start-subscriber").read_text(encoding="utf-8")
        self.assertIn("missing", text)
        self.assertIn("exit 78", text, "EX_CONFIG is the right code for a missing .env")

    def test_start_scripts_do_not_install_dependencies_at_startup(self) -> None:
        """They run inside the runtime project, they do not resolve it again."""
        for name in ("start-mcp", "start-subscriber"):
            with self.subTest(name=name):
                text = (BIN / name).read_text(encoding="utf-8")
                self.assertIn('--project "$KIT/runtime"', text)
                self.assertNotIn("uv sync", text)


class InstallScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = KIT_ROOT / "install.sh"

    def test_install_script_is_executable(self) -> None:
        self.assertTrue(self.script.is_file())
        self.assertTrue(os.access(self.script, os.X_OK))

    def test_install_copies_the_entry_points_and_units(self) -> None:
        text = self.script.read_text(encoding="utf-8")
        for item in ("bin", "systemd", "runtime", "service-template", "libs"):
            with self.subTest(item=item):
                self.assertIn(item, text)
        self.assertIn("chmod +x", text)

    def test_install_copies_every_directory_the_configuration_loads(self) -> None:
        """ai4-z3yq: `build_agent_runtime` reads four roots at startup.

        One of them (`agent-definitions/`) was not in the copy list for a while,
        so an installed kit would have failed to start with a missing directory
        even though the source checkout worked.
        """
        from work_agent_runtime.assembly import SHIPPED

        text = self.script.read_text(encoding="utf-8")
        copy_line = next(line for line in text.splitlines() if line.startswith("for item in"))
        for variable, directory in SHIPPED.items():
            with self.subTest(variable=variable):
                top_level = directory.split("/")[0]
                self.assertIn(top_level, copy_line, f"{variable} points at {directory}, not copied")
                self.assertTrue((KIT_ROOT / directory).is_dir(), f"{directory} is missing from the kit")

    def test_install_never_overwrites_an_existing_env(self) -> None:
        text = self.script.read_text(encoding="utf-8")
        self.assertIn('if [ ! -f "$TARGET/.env" ]', text, "an upgrade must not clobber credentials")

    def test_install_substitutes_the_target_into_the_units(self) -> None:
        """%h/.sciweave/task-agent is the default; a custom home must still work."""
        text = self.script.read_text(encoding="utf-8")
        self.assertIn("sed", text)
        self.assertIn("%h/.sciweave/task-agent", text)

    def test_install_script_passes_a_shell_syntax_check(self) -> None:
        result = subprocess.run(["sh", "-n", str(self.script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class HarnessHookTests(unittest.TestCase):
    """The hook runs on every harness start, so it cannot fail on an uninstalled machine."""

    @unittest.skipUnless(os.name == "posix", "the hook drives systemd user services; it is a POSIX artifact")
    def test_hook_no_longer_fails_when_the_services_are_not_installed(self) -> None:
        script = KIT_ROOT / "hooks" / "check-services.sh"
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"hook failed with {result.returncode}: {result.stderr}")
        self.assertIn("not installed", result.stderr, "it should say why it skipped instead of failing silently")

    def test_hook_only_starts_services_that_are_enabled(self) -> None:
        text = (KIT_ROOT / "hooks" / "check-services.sh").read_text(encoding="utf-8")
        self.assertIn("is-enabled", text)
        self.assertNotIn("systemctl --user stop", text, "the hook must never stop a service")
