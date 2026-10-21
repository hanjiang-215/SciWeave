from __future__ import annotations

import json
import sys
from dataclasses import asdict

from llm_wiki.config import WikiConfig
from llm_wiki.resource_review import ResourceReviewService
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.terminus_store import TerminusDBResourceStore


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv if argv is None else argv
    config = WikiConfig.from_environment()
    sqlite_store = SqliteStore(config.sqlite_path)
    sqlite_store.initialize()
    service = ResourceReviewService(
        sqlite_store=sqlite_store,
        terminus_store=TerminusDBResourceStore(
            base_url=config.terminusdb_url,
            token=config.terminusdb_token,
            username=config.terminusdb_username,
            password=config.terminusdb_password,
        ),
    )
    if len(arguments) > 1:
        qualification = service.get_current_qualification(arguments[1])
        print(json.dumps(asdict(qualification), ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "status": "ready",
                    "domain_id": config.domain_id,
                    "resource_version_read": "unavailable",
                    "reason_code": "exact_version_location_unknown",
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
