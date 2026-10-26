from __future__ import annotations

import os

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CoordinatorConfig:
    sqlite_path: str
    retry_initial_seconds: float
    retry_multiplier: float
    retry_max_seconds: float
    dispatch_poll_seconds: float
    max_attempts: int

    @classmethod
    def from_environment(cls) -> "CoordinatorConfig":
        required = (
            "SCIWEAVE_COORDINATOR_SQLITE_PATH",
            "SCIWEAVE_COORDINATOR_RETRY_INITIAL_SECONDS",
            "SCIWEAVE_COORDINATOR_RETRY_MULTIPLIER",
            "SCIWEAVE_COORDINATOR_RETRY_MAX_SECONDS",
            "SCIWEAVE_COORDINATOR_DISPATCH_POLL_SECONDS",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(f"missing required coordinator configuration: {', '.join(missing)}")
        return cls(
            sqlite_path=os.environ["SCIWEAVE_COORDINATOR_SQLITE_PATH"],
            retry_initial_seconds=_seconds("SCIWEAVE_COORDINATOR_RETRY_INITIAL_SECONDS"),
            retry_multiplier=_multiplier("SCIWEAVE_COORDINATOR_RETRY_MULTIPLIER"),
            retry_max_seconds=_seconds("SCIWEAVE_COORDINATOR_RETRY_MAX_SECONDS"),
            dispatch_poll_seconds=_seconds("SCIWEAVE_COORDINATOR_DISPATCH_POLL_SECONDS"),
            max_attempts=_max_attempts(),
        )

    def with_replacements(self, **values) -> "CoordinatorConfig":
        return replace(self, **values)


def _seconds(name: str) -> float:
    try:
        value = float(os.environ[name])
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative number") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return value


def _multiplier(name: str) -> float:
    value = _seconds(name)
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _max_attempts() -> int:
    raw = os.environ.get("SCIWEAVE_COORDINATOR_MAX_ATTEMPTS", "5").strip()
    if not raw.isdigit():
        raise ValueError("SCIWEAVE_COORDINATOR_MAX_ATTEMPTS must be a positive integer")
    value = int(raw)
    if value < 1:
        raise ValueError("SCIWEAVE_COORDINATOR_MAX_ATTEMPTS must be a positive integer")
    return value