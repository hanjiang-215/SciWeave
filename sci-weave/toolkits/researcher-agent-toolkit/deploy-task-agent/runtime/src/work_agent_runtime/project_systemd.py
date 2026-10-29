"""Project-bound Linux systemd --user service management.

This module deliberately requires an explicit project root.  It never derives a
binding from cwd or the legacy ``~/.sciweave/task-agent`` installation.
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


def _systemd_quote(value: Path) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


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

    ``project_root`` is mandatory and is resolved once at construction.  The
    binding JSON is the source of truth and is updated only by ``generate`` or
    explicit ``rebind``.
    """

    def __init__(self, project_root: os.PathLike[str] | str, *, config_home: os.PathLike[str] | str | None = None):
        if project_root is None:
            raise TypeError("project_root must be explicitly provided")
        root = Path(project_root).expanduser().resolve()
        self.project_root = root
        self.config_home = Path(config_home).expanduser().resolve() if config_home else Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        ).resolve()
        self.paths = ProjectPaths(root, root / ".sciweave" / "runtime", root / ".sciweave" / "data", root / ".sciweave" / ".env")
        self.binding_path = root / ".sciweave" / "runtime" / "project-binding.json"
        existing = self._read_binding()
        self.project_id = existing.get("project_id") if existing else hashlib.sha256(str(root).encode()).hexdigest()[:16]
        self.unit_name = f"sciweave-task-agent-{self.project_id}.service"
        self.unit_path = self.config_home / "systemd" / "user" / self.unit_name

    def _read_binding(self) -> dict:
        try:
            return json.loads(self.binding_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @property
    def runtime_path(self) -> Path:
        return self.paths.runtime

    @property
    def data_path(self) -> Path:
        return self.paths.data

    @property
    def env_path(self) -> Path:
        return self.paths.env

    def _validate(self) -> None:
        if not self.project_root.is_dir():
            raise ProjectBindingStaleError(f"project root is missing; explicit rebind required: {self.project_root}")
        missing = [str(p) for p in (self.paths.runtime, self.paths.data, self.paths.env) if not p.exists()]
        if missing:
            raise ProjectBindingError("project binding paths missing: " + ", ".join(missing))

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

    def generate(self) -> Path:
        self._validate()
        self.binding_path.parent.mkdir(parents=True, exist_ok=True)
        self.binding_path.write_text(json.dumps(self._binding(), indent=2) + "\n", encoding="utf-8")
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        start = self.project_root / ".sciweave" / "runtime" / "bin" / "start-subscriber"
        # The runtime copy is optional in the first layout; the shipped kit
        # entrypoint remains the canonical command when present.
        kit_start = self.project_root / ".sciweave" / "bin" / "start-subscriber"
        if not kit_start.exists():
            kit_start = Path(__file__).resolve().parents[3] / "bin" / "start-subscriber"
        unit = f"""[Unit]\nDescription=SciWeave project-bound Task Agent ({self.project_id})\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory={_systemd_quote(self.paths.runtime)}\nEnvironmentFile={_systemd_quote(self.paths.env)}\nExecStart={_systemd_quote(kit_start)}\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n"""
        self.unit_path.write_text(unit, encoding="utf-8")
        return self.unit_path

    def start(self, *, run_systemctl: bool = True) -> None:
        self._validate()
        binding = self._read_binding()
        if binding.get("project_root") != str(self.project_root):
            raise ProjectBindingStaleError("project binding is stale; explicit rebind required")
        self.generate()
        if run_systemctl:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", self.unit_name], check=True)

    def rebind(self, project_root: os.PathLike[str] | str) -> "ProjectSystemdManager":
        rebound = ProjectSystemdManager(project_root, config_home=self.config_home)
        rebound.project_id = self.project_id
        rebound.unit_name = self.unit_name
        rebound.unit_path = self.unit_path
        rebound.generate()
        return rebound

    @classmethod
    def inspect_legacy(cls, legacy_root: os.PathLike[str] | str) -> LegacyInstallation:
        root = Path(legacy_root).expanduser().resolve()
        binding = root / "project-binding.json"
        if not root.is_dir():
            return LegacyInstallation(root, None, "missing")
        if not binding.is_file():
            return LegacyInstallation(root, None, "unbound")
        try:
            raw = json.loads(binding.read_text(encoding="utf-8"))
            bound = Path(raw["project_root"]).expanduser().resolve()
        except (OSError, ValueError, KeyError):
            return LegacyInstallation(root, None, "ambiguous")
        if not bound.is_dir():
            return LegacyInstallation(root, bound, "stale")
        return LegacyInstallation(root, bound, "bound")

    @classmethod
    def migrate_legacy(
        cls,
        legacy_root: os.PathLike[str] | str,
        project_root: os.PathLike[str] | str,
        *,
        config_home: os.PathLike[str] | str | None = None,
    ) -> "ProjectSystemdManager":
        legacy = cls.inspect_legacy(legacy_root)
        target = Path(project_root).expanduser().resolve()
        if not target.is_dir():
            raise ProjectBindingError("explicit target project root is missing: " + str(target))
        if legacy.status in {"ambiguous", "unbound"}:
            raise ProjectBindingError("legacy installation ownership is unknown; explicit binding metadata is required")
        manager = cls(target, config_home=config_home)
        manager._validate()
        manager.generate()
        return manager

    def uninstall(self, confirmation: UninstallConfirmation | None = None, *, run_systemctl: bool = False) -> None:
        confirmation = confirmation or UninstallConfirmation()
        if confirmation.purge_data and confirmation.token != "PURGE SCIWEAVE DATA":
            raise ProjectBindingError("purging data requires confirmation token: PURGE SCIWEAVE DATA")
        if run_systemctl:
            subprocess.run(["systemctl", "--user", "disable", "--now", self.unit_name], check=False)
        self.unit_path.unlink(missing_ok=True)
        if confirmation.purge_data:
            shutil.rmtree(self.paths.data, ignore_errors=True)
            shutil.rmtree(self.paths.runtime, ignore_errors=True)
        else:
            # Keep project definitions, generated state, credentials and data.
            for child in (self.paths.runtime / "project-binding.json",):
                child.unlink(missing_ok=True)
            if self.paths.runtime.exists() and not any(self.paths.runtime.iterdir()):
                self.paths.runtime.rmdir()
