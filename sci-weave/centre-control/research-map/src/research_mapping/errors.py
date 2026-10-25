from __future__ import annotations


class ConfigError(RuntimeError):
    """Raised when required process configuration is absent."""


# Stable reason codes shared by the formal query service and its tests.
OK = "ok"
NO_CURRENT_POINTER = "no_current_pointer"
POINTER_REVISION_MISSING = "pointer_revision_missing"
POINTER_DOMAIN_MISMATCH = "pointer_domain_mismatch"
REVISION_NOT_FOUND = "revision_not_found"
SUCCEEDED_RESULT_MISSING = "succeeded_result_missing"
SUCCEEDED_RESULT_MISMATCH = "succeeded_result_mismatch"
COMMIT_MISSING = "commit_missing"
STORE_UNAVAILABLE = "store_unavailable"
STORE_RESULT_UNKNOWN = "store_result_unknown"
SNAPSHOT_IDENTITY_MISMATCH = "snapshot_identity_mismatch"
SNAPSHOT_DIGEST_MISMATCH = "snapshot_digest_mismatch"
SNAPSHOT_NODE_COUNT_MISMATCH = "snapshot_node_count_mismatch"
SNAPSHOT_EDGE_COUNT_MISMATCH = "snapshot_edge_count_mismatch"
DATA_VERSION_MISSING = "data_version_missing"
DATA_VERSION_MISMATCH = "data_version_mismatch"
UNEXPECTED_CONTENT_TYPE = "unexpected_content_type"
UNEXPECTED_PAYLOAD = "unexpected_payload"
