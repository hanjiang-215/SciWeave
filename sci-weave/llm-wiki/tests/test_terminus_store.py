from __future__ import annotations

import base64
import json
import unittest

from llm_wiki.canonical import sha256_json
from llm_wiki.domain import ResourceVersionLocation
from llm_wiki.terminus_store import TerminusDBResourceStore

STORE = "admin"
DATABASE = "wiki-it"
BRANCH = "main"
COMMIT = "a" * 40
VERSION = "rv-1"

LOCATION = ResourceVersionLocation(
    store_id=STORE, database=DATABASE, branch_id=BRANCH, commit_hash=COMMIT
)

RESOURCE = {
    "@id": "Resource/res-1",
    "@type": "Resource",
    "resource_id": "res-1",
    "owner_id": "owner-1",
}
VERSION_DOCUMENT = {
    "@id": "ResourceVersion/rv-1",
    "@type": "ResourceVersion",
    "resource_version_id": VERSION,
    "resource_id": "Resource/res-1",
    "source_locator": "doi:10.0000/example",
    "source_external_id": "external-1",
    "external_version_id": "upstream-v1",
    "current_access_locator": "https://example.org/items/1",
    "availability_status": "available",
    "availability_checked_at": "2026-10-20T00:00:00Z",
    "generated_at": "2026-10-19T00:00:00Z",
    "generated_by": "task-agent-1",
    "generated_by_task_id": "task-1",
    "license": "CC-BY-4.0",
    "attribution": "Example Lab",
    "handling_mode": "direct_query",
    "content_checksum_algorithm": "sha256",
    "content_checksum_value": "b" * 64,
}


def confirmed_responder(payload, captured=None, data_version=f"commit:{COMMIT}"):
    def opener(url, headers, timeout):
        if captured is not None:
            captured["url"] = url
            captured["headers"] = headers
        return (
            200,
            {
                "content-type": "application/json; charset=UTF-8",
                "Terminusdb-Data-Version": data_version,
            },
            json.dumps(payload).encode("utf-8"),
        )

    return opener


class TerminusDBResourceStoreTestCase(unittest.TestCase):
    def adapter(self, opener, **kwargs) -> TerminusDBResourceStore:
        return TerminusDBResourceStore(
            base_url="http://127.0.0.1:0",
            remote="local",
            opener=opener,
            **kwargs,
        )

    def test_confirmed_read_uses_the_exact_commit_route(self) -> None:
        captured = {}
        adapter = self.adapter(confirmed_responder([RESOURCE, VERSION_DOCUMENT], captured))

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)
        self.assertEqual(
            captured["url"],
            f"http://127.0.0.1:0/api/document/{STORE}/{DATABASE}/local/commit/"
            f"{COMMIT}?as_list=true&graph_type=instance",
        )
        self.assertEqual(
            captured["headers"]["TerminusDB-Data-Version"], f"commit:{COMMIT}"
        )

    def test_snapshot_maps_version_facts_and_resolves_the_resource_owner(self) -> None:
        adapter = self.adapter(confirmed_responder([RESOURCE, VERSION_DOCUMENT]))

        snapshot = adapter.read_resource_version(LOCATION, VERSION).snapshot

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.resource_version_id, VERSION)
        self.assertEqual(snapshot.resource_id, "Resource/res-1")
        self.assertEqual(snapshot.owner_id, "owner-1")
        self.assertEqual(snapshot.snapshot_digest, sha256_json(VERSION_DOCUMENT))
        self.assertEqual(snapshot.content_digest, "b" * 64)
        self.assertEqual(snapshot.content_checksum_algorithm, "sha256")
        self.assertEqual(snapshot.license, "CC-BY-4.0")
        self.assertEqual(snapshot.attribution, "Example Lab")
        self.assertEqual(snapshot.handling_mode, "direct_query")
        self.assertEqual(snapshot.source_locator, "doi:10.0000/example")
        self.assertEqual(snapshot.external_version_id, "upstream-v1")
        self.assertEqual(snapshot.availability_status, "available")

    def test_document_id_suffix_also_identifies_the_version(self) -> None:
        document = dict(VERSION_DOCUMENT)
        document.pop("resource_version_id")
        adapter = self.adapter(confirmed_responder([RESOURCE, document]))

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)

    def test_missing_resource_document_leaves_the_owner_unknown(self) -> None:
        adapter = self.adapter(confirmed_responder([VERSION_DOCUMENT]))

        snapshot = adapter.read_resource_version(LOCATION, VERSION).snapshot

        self.assertIsNotNone(snapshot)
        self.assertIsNone(snapshot.owner_id)
        self.assertIn("owner_id", snapshot.derive_unknown_facts())

    def test_absent_version_in_a_readable_snapshot_is_missing(self) -> None:
        adapter = self.adapter(confirmed_responder([RESOURCE]))

        outcome = adapter.read_resource_version(LOCATION, "rv-unknown")

        self.assertEqual(outcome.status, "missing")
        self.assertEqual(outcome.reason_code, "version_missing")
        self.assertIsNone(outcome.snapshot)

    def test_two_documents_claiming_the_same_version_are_unavailable(self) -> None:
        duplicate = dict(VERSION_DOCUMENT)
        duplicate["@id"] = "ResourceVersion/rv-1-copy"
        adapter = self.adapter(confirmed_responder([RESOURCE, VERSION_DOCUMENT, duplicate]))

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "version_id_ambiguous")

    def test_commit_not_found_is_missing(self) -> None:
        adapter = self.adapter(lambda url, headers, timeout: (404, {}, b"{}"))

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "missing")
        self.assertEqual(outcome.reason_code, "version_missing")

    def test_unknown_commit_server_error_is_unavailable(self) -> None:
        adapter = self.adapter(lambda url, headers, timeout: (500, {}, b"boom"))

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "store_unavailable")

    def test_data_version_mismatch_is_unavailable(self) -> None:
        adapter = self.adapter(
            confirmed_responder(
                [RESOURCE, VERSION_DOCUMENT], data_version="commit:" + "c" * 40
            )
        )

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "data_version_mismatch")

    def test_missing_data_version_header_is_unavailable(self) -> None:
        def opener(url, headers, timeout):
            return (
                200,
                {"content-type": "application/json"},
                json.dumps([RESOURCE, VERSION_DOCUMENT]).encode("utf-8"),
            )

        outcome = self.adapter(opener).read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "data_version_missing")

    def test_non_json_content_type_is_unavailable(self) -> None:
        def opener(url, headers, timeout):
            return (
                200,
                {"content-type": "text/html", "Terminusdb-Data-Version": f"commit:{COMMIT}"},
                b"<html></html>",
            )

        outcome = self.adapter(opener).read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "unexpected_content_type")

    def test_non_list_payload_is_unavailable(self) -> None:
        adapter = self.adapter(confirmed_responder({"not": "a list"}))

        outcome = adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "unexpected_payload")

    def test_transport_error_is_unavailable(self) -> None:
        def opener(url, headers, timeout):
            raise OSError("connection refused")

        outcome = self.adapter(opener).read_resource_version(LOCATION, VERSION)

        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason_code, "store_unavailable")

    def test_basic_credentials_replace_the_bearer_header(self) -> None:
        captured = {}
        adapter = self.adapter(
            confirmed_responder([RESOURCE, VERSION_DOCUMENT], captured),
            username="admin",
            password="root",
        )

        adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(
            captured["headers"]["Authorization"],
            "Basic " + base64.b64encode(b"admin:root").decode("ascii"),
        )

    def test_bearer_token_is_used_when_configured(self) -> None:
        captured = {}
        adapter = self.adapter(
            confirmed_responder([RESOURCE, VERSION_DOCUMENT], captured),
            token="token-1",
        )

        adapter.read_resource_version(LOCATION, VERSION)

        self.assertEqual(captured["headers"]["Authorization"], "Bearer token-1")

    def test_token_and_basic_credentials_are_rejected_together(self) -> None:
        with self.assertRaises(ValueError):
            TerminusDBResourceStore(
                base_url="http://127.0.0.1:0",
                token="token-1",
                username="admin",
                password="root",
            )

    def test_location_requires_every_segment(self) -> None:
        with self.assertRaises(ValueError):
            ResourceVersionLocation(
                store_id="admin", database="wiki", branch_id="main", commit_hash=""
            )


if __name__ == "__main__":
    unittest.main()
