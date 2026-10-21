from __future__ import annotations


class ConfigError(RuntimeError):
    """Raised when required process configuration is absent."""


# Stable reason codes shared by the review service and its tests.
DECISION_RECORDED = "decision_recorded"
NO_EFFECTIVE_DECISION = "no_effective_decision"
VERSION_MISSING = "version_missing"
VERSION_ID_MISMATCH = "version_id_mismatch"
VERSION_ID_AMBIGUOUS = "version_id_ambiguous"
STORE_UNAVAILABLE = "store_unavailable"
OWNER_UNKNOWN = "owner_unknown"
AUTHORITY_MISSING = "authority_missing"
AUTHORITY_UNVERIFIED = "authority_unverified"
EXACT_VERSION_LOCATION_UNKNOWN = "exact_version_location_unknown"
UNEXPECTED_CONTENT_TYPE = "unexpected_content_type"
DATA_VERSION_MISSING = "data_version_missing"
DATA_VERSION_MISMATCH = "data_version_mismatch"
UNEXPECTED_PAYLOAD = "unexpected_payload"
