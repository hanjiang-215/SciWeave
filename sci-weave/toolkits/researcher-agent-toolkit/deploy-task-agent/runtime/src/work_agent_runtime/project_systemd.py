"""Project-bound Linux systemd --user service management.

This module deliberately requires an explicit project root. It never derives a
binding from cwd or the legacy ``~/.sciweave/task-agent`` installation, and it
never guesses which project an unbound legacy directory belonged to.

One project instance owns exactly one unit. The unit name carries a stable
project id, so two projects can run side by side without sharing code, SQLite,
sessions, logs or service state.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ProjectBindingError(RuntimeError):
    """The project binding cannot be safely used."""


class ProjectBindingStaleError(ProjectBindingError):
    """The project moved; an explicit rebind is required."""


#: The only accepted confirmation for deleting runtime data.
PURGE_TOKEN = "PURGE SCIWEAVE DATA"


def _systemd_path(value: Path | str) -> str:
    """Render a path for a systemd unit.

    systemd does not accept a quoted path here, and a raw space splits the
    value. Escaping spaces as ``\\x20`` is the documented form and keeps
    ``systemd-analyze verify`` happy whether or not the directory exists yet.
    """
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ProjectBindingError("project paths must not contain newlines")
    return text.replace("\\", "\\\\").replace(" ", "\\x20").replace("%", "%%")


def project_id_for(root: Path) -> str:
    """A stable id for a project root. Renaming the directory changes it."""
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    runtime: Path
    data: Path
    env: Path


@dataclass(frozen=True)
class LegacyInstallation:
    root: Path
    bound_project: Path | None
    status: str


@dataclass(frozen=True)
class UninstallConfirmation:
    purge_data: bool = False
    token: str = ""


class ProjectSystemdManager:
    """Manage one project-specific subscriber service.

    ``project_root`` is mandatory and is resolved once at construction. The
    binding JSON is the source of truth and is rewritten only by ``generate``,
    ``upgrade`` or an explicit ``rebind``.
    """

    def __init__(
        self,
        project_root: os.PathLike[str] | str,
        *,
        config_home: os.PathLike[str] | str | None = None,
    ):
        if project_root is None:
            raise TypeError("project_root must be explicitly provided")
        root = Path(project_root).expanduser().resolve()
        self.project_root = root
        self.config_home = Path(
            config_home or os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        ).expanduser().resolve()
        self.paths = ProjectPaths(
            root,
            root / ".sciweave" / "runtime",
            root / ".sciweave" / "data",
            root / ".sciweave" / ".env",
        )
        self.binding_path = self.paths.runtime / "project-binding.json"
        existing = self._read_binding()
        self.project_id = existing.get("project_id") or project_id_for(root)
        self.unit_name = f"sciweave-task-agent-{self.project_id}.service"
        self.unit_path = self.config_home / "systemd" / "user" / self.unit_name

    # -- paths -----------------------------------------------------------

    @property
    def runtime_path(self) -> Path:
        return self.paths.runtime

    @property
    def data_path(self) -> Path:
        return self.paths.data

    @property
    def env_path(self) -> Path:
        return self.paths.env

    @property
    def sessions_path(self) -> Path:
        return self.paths.data / "sessions"

    @property
    def logs_path(self) -> Path:
        return self.paths.data / "logs"

    # -- binding ---------------------------------------------------------

    def _read_binding(self) -> dict:
        try:
            data = json.loads(self.binding_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _binding(self) -> dict:
        return {
            "version": 1,
            "project_id": self.project_id,
            "project_root": str(self.project_root),
            "runtime": str(self.paths.runtime),
            "data": str(self.paths.data),
            "env": str(self.paths.env),
            "unit": self.unit_name,
        }

    def _validate_paths(self) -> None:
        if not self.project_root.is_dir():
            raise ProjectBindingStaleError(
                f"project root is missing; explicit rebind required: {self.project_root}"
            )
        # ``.env`` is optional (spec §4): a project may inject the environment
        # externally instead. Only the runtime and data directories must exist.
        missing = [str(p) for p in (self.paths.runtime, self.paths.data) if not p.exists()]
        if missing:
            raise ProjectBindingError("project binding paths missing: " + ", ".join(missing))

    def _require_current_binding(self) -> None:
        """Refuse to act on a stale binding instead of silently re-pointing it."""
        binding = self._read_binding()
        if not binding:
            raise ProjectBindingError(
                "no project binding; run generate (new instance) or migrate (legacy instance) first"
            )
        if binding.get("project_root") != str(self.project_root):
            raise ProjectBindingStaleError(
                "project binding is stale; explicit rebind required: "
                f"bound to {binding.get('project_root')}, now {self.project_root}"
            )

    # -- generation ------------------------------------------------------

    def _entrypoint(self) -> Path:
        """The command systemd starts: project instance first, shipped kit last."""
        for candidate in (
            self.paths.runtime / "bin" / "start-subscriber",
            self.project_root / ".sciweave" / "bin" / "start-subscriber",
        ):
            if candidate.exists():
                return candidate
        return self.paths.runtime / "bin" / "start-subscriber"

    def _render_unit(self) -> str:
        return (
            "[Unit]\n"
            f"Description=SciWeave project-bound Task Agent ({self.project_id})\n"
            "After=network-online.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={_systemd_path(self.paths.runtime)}\n"
            f"Environment=\"SCIWEAVE_PROJECT_ROOT={_systemd_path(self.project_root)}\"" + "\n"
            f"EnvironmentFile=-{_systemd_path(self.paths.env)}\n"
            f"ExecStart={_systemd_path(self._entrypoint())}\n"
            "Restart=on-failure\n"
            "RestartSec=2\n"
            f"StandardOutput=append:{_systemd_path(self.logs_path / 'service.log')}\n"
            f"StandardError=append:{_systemd_path(self.logs_path / 'service.log')}\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def generate(self) -> Path:
        """Create the project instance directories and write the binding and unit.

        Creation comes first so a brand-new project can be initialised; only
        afterwards is the layout validated, which then also catches a project
        root that vanished between construction and this call.
        """
        if not self.project_root.is_dir():
            raise ProjectBindingStaleError(
                f"project root is missing; explicit rebind required: {self.project_root}"
            )
        self.paths.runtime.mkdir(parents=True, exist_ok=True)
        self.paths.data.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        self._validate_paths()
        self.binding_path.write_text(json.dumps(self._binding(), indent=2) + "\n", encoding="utf-8")
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text(self._render_unit(), encoding="utf-8")
        return self.unit_path

    # -- lifecycle -------------------------------------------------------

    def _systemctl(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["systemctl", "--user", *args], check=check, capture_output=True, text=True
        )

    def start(self, *, run_systemctl: bool = True) -> None:
        """Start the instance, creating the binding on first use.

        An existing binding that points somewhere else is refused: only an
        explicit ``rebind`` may re-point an already-bound instance.
        """
        if not self.project_root.is_dir():
            raise ProjectBindingStaleError(
                f"project root is missing; explicit rebind required: {self.project_root}"
            )
        if self._read_binding():
            self._require_current_binding()
        self.generate()
        if not run_systemctl:
            return
        self._systemctl("daemon-reload")
        self._systemctl("enable", "--now", self.unit_name)

    def stop(self, *, run_systemctl: bool = True) -> None:
        if run_systemctl:
            self._systemctl("disable", "--now", self.unit_name, check=False)

    def restart(self, *, run_systemctl: bool = True) -> None:
        if run_systemctl:
            self._systemctl("restart", self.unit_name)

    def unit_state(self, *, run_systemctl: bool = True) -> str:
        """``active``, ``inactive``, ``failed`` … or ``unknown`` when systemd is absent."""
        if not run_systemctl:
            return "unknown"
        result = self._systemctl("is-active", self.unit_name, check=False)
        return result.stdout.strip() or "unknown"

    def restart_count(self) -> int:
        result = self._systemctl(
            "show", self.unit_name, "--property=NRestarts", "--value", check=False
        )
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    def logs(self, lines: int = 50, *, source: str = "journal") -> str:
        """Service output, from the journal or from the instance's own log file."""
        if source == "file":
            log = self.logs_path / "service.log"
            return log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        result = subprocess.run(
            ["journalctl", "--user", "-u", self.unit_name, "-n", str(lines), "--no-pager", "--output=cat"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def upgrade(self, *, manifest: os.PathLike[str] | str | None = None) -> None:
        """Refresh runtime code and the unit, keeping the user's own state.

        Validation happens before anything is replaced, so a failed upgrade
        leaves the previous version runnable.
        """
        if not self.project_root.is_dir():
            raise ProjectBindingStaleError(
                f"project root is missing; explicit rebind required: {self.project_root}"
            )
        self._require_current_binding()
        self._validate_paths()
        if manifest is not None:
            candidate = Path(manifest).expanduser()
            if not candidate.is_file() or not candidate.read_text(encoding="utf-8").strip():
                raise ProjectBindingError(
                    f"manifest validation failed, previous version left in place: {candidate}"
                )
        self.generate()

    def rebind(self, project_root: os.PathLike[str] | str) -> "ProjectSystemdManager":
        """Point the existing unit at a new project root, on explicit request only."""
        rebound = ProjectSystemdManager(project_root, config_home=self.config_home)
        rebound.project_id = self.project_id
        rebound.unit_name = self.unit_name
        rebound.unit_path = self.unit_path
        rebound.generate()
        return rebound

    def uninstall(
        self,
        confirmation: UninstallConfirmation | None = None,
        *,
        run_systemctl: bool = True,
    ) -> None:
        """Remove the service registration and runtime code.

        ``data/``, ``project/`` and ``.env`` survive: deleting runtime data is a
        separate, explicitly confirmed operation.
        """
        confirmation = confirmation or UninstallConfirmation()
        if confirmation.purge_data and confirmation.token != PURGE_TOKEN:
            raise ProjectBindingError(f"purging data requires confirmation token: {PURGE_TOKEN}")
        self.stop(run_systemctl=run_systemctl)
        self.unit_path.unlink(missing_ok=True)
        if run_systemctl:
            self._systemctl("daemon-reload", check=False)
        if confirmation.purge_data:
            shutil.rmtree(self.paths.data, ignore_errors=True)
        shutil.rmtree(self.paths.runtime, ignore_errors=True)

    # -- legacy ----------------------------------------------------------

    @classmethod
    def inspect_legacy(cls, legacy_root: os.PathLike[str] | str) -> LegacyInstallation:
        """Report what a legacy install is, without deciding what it belongs to."""
        root = Path(legacy_root).expanduser().resolve()
        if not root.is_dir():
            return LegacyInstallation(root, None, "missing")
        binding = root / "project-binding.json"
        if not binding.is_file():
            return LegacyInstallation(root, None, "unbound")
        try:
            bound = Path(json.loads(binding.read_text(encoding="utf-8"))["project_root"]).expanduser().resolve()
        except (OSError, ValueError, KeyError, TypeError):
            return LegacyInstallation(root, None, "ambiguous")
        if not bound.is_dir():
            return LegacyInstallation(root, bound, "stale")
        return LegacyInstallation(root, bound, "bound")

    @classmethod
    def describe_legacy(
        cls,
        legacy_root: os.PathLike[str] | str,
        *,
        config_home: os.PathLike[str] | str | None = None,
    ) -> dict:
        """What a migration would carry: code, state, services and configuration."""
        state = cls.inspect_legacy(legacy_root)
        entries = []
        if state.root.is_dir():
            entries = sorted(p.name for p in state.root.iterdir())
        config = Path(
            config_home or os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        ).expanduser().resolve()
        return {
            "root": str(state.root),
            "status": state.status,
            "bound_project": str(state.bound_project) if state.bound_project else None,
            "entries": entries,
            "unit_files": sorted(
                p.name for p in (config / "systemd" / "user").glob("sciweave-task-agent*.service")
            ),
        }

    @classmethod
    def migrate_legacy(
        cls,
        legacy_root: os.PathLike[str] | str,
        project_root: os.PathLike[str] | str,
        *,
        config_home: os.PathLike[str] | str | None = None,
        run_systemctl: bool = False,
    ) -> "ProjectSystemdManager":
        """Copy a legacy install onto an explicitly chosen project root.

        Code and state move by copy, never by delete: the legacy directory is
        left intact so a half-finished migration cannot destroy the only copy.
        An existing target ``data/`` or ``project/`` is never overwritten.
        """
        legacy = cls.inspect_legacy(legacy_root)
        target = Path(project_root).expanduser().resolve()
        if not target.is_dir():
            raise ProjectBindingError("explicit target project root is missing: " + str(target))
        if legacy.status in {"ambiguous", "unbound"}:
            raise ProjectBindingError(
                "legacy installation ownership is unknown; explicit binding metadata is required"
            )
        source = legacy.root
        manager = cls(target, config_home=config_home)
        manager.paths.runtime.mkdir(parents=True, exist_ok=True)
        manager.paths.data.mkdir(parents=True, exist_ok=True)
        cls._adopt(source, manager.paths.runtime, {"project-binding.json"})
        cls._adopt(source / "data", manager.paths.data)
        manager.generate()
        if run_systemctl:
            manager.stop(run_systemctl=True)
            manager.start(run_systemctl=True)
        return manager

    @staticmethod
    def _adopt(source: Path, destination: Path, skip: set[str] | None = None) -> None:
        """Copy missing files from ``source`` into ``destination`` without clobbering."""
        if not source.is_dir():
            return
        skip = skip or set()
        for entry in source.iterdir():
            if entry.name in skip:
                continue
            target = destination / entry.name
            if target.exists():
                continue  # never overwrite the target's own state
            if entry.is_dir():
                shutil.copytree(entry, target, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git"))
            else:
                shutil.copy2(entry, target)
