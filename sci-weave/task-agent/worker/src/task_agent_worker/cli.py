"""Task Agent Worker console-script entry point."""

from __future__ import annotations

from .config import WorkerSettings


def main() -> None:
    """Validate Worker model settings before Gateway starts short-lived loops."""
    settings = WorkerSettings.from_environment()
    settings.validate_for_model_call()
    print(f"Worker configuration is ready for model {settings.model}.")
