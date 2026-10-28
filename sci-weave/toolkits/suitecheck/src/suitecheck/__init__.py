"""Static validation for SciWeave Agent suites.

A suite is one directory an Agent can be handed whole: a manifest plus the
skills, MCP cards, hooks, cron units and install/check commands it declares.
Nothing here executes a declared command; ``checks`` only proves every command
is *runnable in shape* (declared, non-empty argv). Use ``suitecheck run`` to
execute them, which is a separate, explicit decision.
"""

from .manifest import (
    MANIFEST_NAME,
    ROLES,
    ROLE_CAPABILITIES,
    SuiteManifest,
    load_manifest,
    ManifestError,
)
from .validate import Finding, Severity, validate_suite, find_suites

__all__ = [
    "MANIFEST_NAME",
    "ROLES",
    "ROLE_CAPABILITIES",
    "SuiteManifest",
    "load_manifest",
    "ManifestError",
    "Finding",
    "Severity",
    "validate_suite",
    "find_suites",
]
