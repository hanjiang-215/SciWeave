from __future__ import annotations

from datetime import datetime, timezone

from .domain import SNAPSHOT_CONFIRMED
from .sqlite_store import SqliteStore
from .terminus_store import TerminusDBStore


def ensure_initial_formal_revision(
    *, sqlite_store: SqliteStore, terminus_store: TerminusDBStore, mapping_domain_id: str
):
    """Ensure the empty formal snapshot exists without overwriting live state."""
    current = sqlite_store.get_current_formal_revision_id(mapping_domain_id)
    if current is not None:
        revision = sqlite_store.get_formal_revision(current)
        if revision is None or revision.mapping_domain_id != mapping_domain_id:
            raise RuntimeError("formal_bootstrap_conflict")
        return revision
    snapshot = terminus_store.ensure_empty_formal_snapshot(mapping_domain_id)
    if snapshot.status != SNAPSHOT_CONFIRMED or snapshot.documents:
        raise RuntimeError(
            f"formal_bootstrap_terminus_{snapshot.status}:{snapshot.reason_code or 'unconfirmed'}"
        )
    return sqlite_store.ensure_initial_formal_revision(
        mapping_domain_id=mapping_domain_id,
        terminus_store_id=snapshot.store_id or "",
        formal_branch_id=snapshot.branch_id or "",
        formal_commit_hash=snapshot.commit_hash or "",
        graph_snapshot_digest=snapshot.content_digest or "",
        published_at=datetime.now(timezone.utc).isoformat(),
    )
