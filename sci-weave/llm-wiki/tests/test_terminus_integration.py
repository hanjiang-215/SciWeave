from __future__ import annotations

import base64
import json
import os
import unittest
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from typing import Any

from llm_wiki.domain import ResourceVersionLocation
from llm_wiki.terminus_store import TerminusDBResourceStore

REQUIRED_VARIABLES = (
    "SCIWEAVE_WIKI_TERMINUSDB_URL",
    "SCIWEAVE_WIKI_TERMINUSDB_DATABASE",
    "SCIWEAVE_WIKI_TERMINUSDB_STORE",
)

VERSION = "rv-integration-1"
RESOURCE_ID = "Resource/res-integration-1"
ORIGINAL_LICENSE = "CC-BY-4.0"
UPDATED_LICENSE = "CC-BY-4.0-updated"
CONTENT_DIGEST = "a" * 64
OWNER = "owner-integration-1"


class TerminusDBResourceVersionIntegrationTestCase(unittest.TestCase):
    """Opt-in check against the pinned TerminusDB 12.0.8 service.

    The test seeds its own temporary database, captures the commit that pinned
    one ResourceVersion, then mutates that resource version in a later commit.
    Reading the historical commit must return the original facts, which proves
    the adapter did not fall back to the branch head.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 "
                "and start the pinned TerminusDB service"
            )
        missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
        if missing:
            raise AssertionError(
                "integration configuration missing: " + ", ".join(missing)
            )

        cls.base_url = os.environ["SCIWEAVE_WIKI_TERMINUSDB_URL"].rstrip("/")
        cls.store = os.environ["SCIWEAVE_WIKI_TERMINUSDB_STORE"]
        configured_database = os.environ["SCIWEAVE_WIKI_TERMINUSDB_DATABASE"]
        cls.database = _temporary_database_name(configured_database)
        cls.remote = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_REMOTE", "local")
        cls.branch = os.environ.get("SCIWEAVE_WIKI_INTEGRATION_BRANCH", "main")
        cls.authorization = _authorization_from_environment()

        cls.adapter = TerminusDBResourceStore(
            base_url=cls.base_url,
            token=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
            username=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
            remote=cls.remote,
        )

        cls._request("DELETE", f"/api/db/{cls.store}/{cls.database}")
        status, _, body = cls._request(
            "POST",
            f"/api/db/{cls.store}/{cls.database}",
            {"label": "SciWeave Wiki Integration", "comment": "exact version read"},
        )
        if status != 200:
            raise AssertionError(f"database creation failed: {status} {body[:400]}")

        cls._register_database_cleanup()

        status, _, body = cls._request(
            "POST",
            f"/api/document/{cls.store}/{cls.database}"
            "?graph_type=schema&author=it&message=define-schema",
            _schema(),
        )
        if status != 200:
            raise AssertionError(f"schema definition failed: {status} {body[:400]}")

        status, _, body = cls._request(
            "POST",
            f"/api/document/{cls.store}/{cls.database}?author=it&message=seed",
            [_resource_document(), _version_document(ORIGINAL_LICENSE)],
        )
        if status != 200:
            raise AssertionError(f"seed failed: {status} {body[:400]}")
        cls.historical_commit = cls._head_commit()

        status, _, body = cls._request(
            "PUT",
            f"/api/document/{cls.store}/{cls.database}"
            "?author=it&message=update-license",
            [_version_document(UPDATED_LICENSE)],
        )
        if status != 200:
            raise AssertionError(f"version update failed: {status} {body[:400]}")
        cls.head_commit = cls._head_commit()
        if cls.historical_commit == cls.head_commit:
            raise AssertionError("historical and head commits must differ")

    @classmethod
    def _register_database_cleanup(cls) -> None:
        cls.addClassCleanup(cls._delete_database)

    @classmethod
    def _delete_database(cls) -> None:
        cls._request("DELETE", f"/api/db/{cls.store}/{cls.database}")

    @classmethod
    def _head_commit(cls) -> str:
        status, _, body = cls._request(
            "GET",
            f"/api/log/{cls.store}/{cls.database}/{cls.remote}"
            f"/branch/{cls.branch}?count=1",
        )
        if status != 200:
            raise AssertionError(f"log read failed: {status} {body[:400]}")
        entries = json.loads(body.decode("utf-8"))
        return str(entries[0]["identifier"])

    @classmethod
    def _request(
        cls,
        method: str,
        path: str,
        payload: Any | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        headers = {"Accept": "application/json"}
        if cls.authorization:
            headers["Authorization"] = cls.authorization
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            cls.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers or {}), error.read()

    def location(self, commit: str) -> ResourceVersionLocation:
        return ResourceVersionLocation(
            store_id=self.store,
            database=self.database,
            branch_id=self.branch,
            commit_hash=commit,
        )

    def test_historical_commit_returns_the_pinned_version(self) -> None:
        outcome = self.adapter.read_resource_version(
            self.location(self.historical_commit), VERSION
        )

        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)
        snapshot = outcome.snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.resource_version_id, VERSION)
        self.assertEqual(snapshot.resource_id, RESOURCE_ID)
        self.assertEqual(snapshot.owner_id, OWNER)
        self.assertEqual(snapshot.content_digest, CONTENT_DIGEST)
        self.assertEqual(snapshot.license, ORIGINAL_LICENSE)
        self.assertIsNotNone(snapshot.snapshot_digest)
        self.assertEqual(len(snapshot.snapshot_digest or ""), 64)

    def test_branch_head_contains_the_later_mutation(self) -> None:
        outcome = self.adapter.read_resource_version(
            self.location(self.head_commit), VERSION
        )

        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)
        snapshot = outcome.snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.license, UPDATED_LICENSE)

    def test_exact_read_does_not_return_the_branch_head(self) -> None:
        historical = self.adapter.read_resource_version(
            self.location(self.historical_commit), VERSION
        )
        head = self.adapter.read_resource_version(
            self.location(self.head_commit), VERSION
        )

        self.assertEqual(historical.status, "confirmed", historical.reason_code)
        self.assertEqual(head.status, "confirmed", head.reason_code)
        self.assertNotEqual(
            historical.snapshot.license,
            head.snapshot.license,
            "historical read must not fall back to the branch head",
        )
        self.assertNotEqual(
            historical.snapshot.snapshot_digest,
            head.snapshot.snapshot_digest,
            "each commit must produce its own snapshot digest",
        )

    def test_absent_version_in_a_readable_commit_is_missing(self) -> None:
        outcome = self.adapter.read_resource_version(
            self.location(self.historical_commit), "rv-not-inserted"
        )

        self.assertEqual(outcome.status, "missing", outcome.reason_code)
        self.assertEqual(outcome.reason_code, "version_missing")
        self.assertIsNone(outcome.snapshot)

    def test_unknown_commit_is_unavailable(self) -> None:
        # Measured on the pinned container: an unknown commit is answered with
        # HTTP 500, never 404, so absence cannot be proven and the adapter must
        # report ``unavailable``.
        outcome = self.adapter.read_resource_version(
            self.location("0" * 40), VERSION
        )

        self.assertEqual(outcome.status, "unavailable", outcome.reason_code)
        self.assertEqual(outcome.reason_code, "store_unavailable")
        self.assertIsNone(outcome.snapshot)


def _temporary_database_name(configured: str) -> str:
    prefix = "".join(
        character if character.isalnum() else "_" for character in configured.lower()
    ).strip("_")
    return f"{prefix or 'sciweave_wiki'}_it_{uuid.uuid4().hex[:8]}"


def _authorization_from_environment() -> str | None:
    token = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN")
    username = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME")
    password = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD")
    if token:
        return f"Bearer {token}"
    if username and password:
        credentials = f"{username}:{password}".encode("utf-8")
        return "Basic " + base64.b64encode(credentials).decode("ascii")
    if username or password:
        raise AssertionError(
            "integration credentials need both username and password"
        )
    return None


def _schema() -> list[dict[str, Any]]:
    return [
        {
            "@type": "Class",
            "@id": "Resource",
            "@key": {"@type": "Lexical", "@fields": ["name"]},
            "name": "xsd:string",
            "owner_id": "xsd:string",
        },
        {
            "@type": "Class",
            "@id": "ResourceVersion",
            "@key": {"@type": "Lexical", "@fields": ["resource_version_id"]},
            "resource_version_id": "xsd:string",
            "resource_id": "xsd:string",
            "content_checksum_algorithm": "xsd:string",
            "content_checksum_value": "xsd:string",
            "license": "xsd:string",
            "attribution": "xsd:string",
            "source_locator": "xsd:string",
            "external_version_id": "xsd:string",
            "current_access_locator": "xsd:string",
            "availability_status": "xsd:string",
            "availability_checked_at": "xsd:string",
            "generated_at": "xsd:string",
            "generated_by": "xsd:string",
            "generated_by_task_id": "xsd:string",
            "handling_mode": "xsd:string",
        },
    ]


def _resource_document() -> dict[str, Any]:
    return {
        "@type": "Resource",
        "@id": RESOURCE_ID,
        "name": "res-integration-1",
        "owner_id": OWNER,
    }


def _version_document(license_value: str) -> dict[str, Any]:
    return {
        "@type": "ResourceVersion",
        "@id": f"ResourceVersion/{VERSION}",
        "resource_version_id": VERSION,
        "resource_id": RESOURCE_ID,
        "content_checksum_algorithm": "sha256",
        "content_checksum_value": CONTENT_DIGEST,
        "license": license_value,
        "attribution": "Integration Lab",
        "source_locator": "doi:10.0000/integration",
        "external_version_id": "upstream-integration-1",
        "current_access_locator": "https://example.org/integration/1",
        "availability_status": "available",
        "availability_checked_at": "2026-10-21T00:00:00Z",
        "generated_at": "2026-10-20T00:00:00Z",
        "generated_by": "integration-agent",
        "generated_by_task_id": "integration-task",
        "handling_mode": "direct_query",
    }


if __name__ == "__main__":
    unittest.main()
