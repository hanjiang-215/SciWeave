from __future__ import annotations

import unittest

from draft_buffer import BufferError
from draft_buffer.store import TerminusDBDraftStore


class StoreAdapterTests(unittest.TestCase):
    def test_initializes_random_key_draft_schema_and_two_namespaces_in_one_database(self):
        adapter = TerminusDBDraftStore(base_url="http://127.0.0.1:0", database="drafts", username="user", password="pass")
        captured = {}
        def request(method, path, payload=None):
            captured.update(method=method, path=path, payload=payload)
            return 200, {}, b"{}"
        adapter.request = request
        adapter.initialize_schema()
        self.assertIn("drafts", captured["path"])
        self.assertEqual(captured["payload"][0]["@key"], {"@type": "Random"})
        self.assertEqual(captured["payload"][1]["@key"], {"@type": "Random"})
        self.assertEqual(len(captured["payload"]), 3)

    def test_write_timeout_is_not_reported_as_confirmed_success(self):
        adapter = TerminusDBDraftStore(base_url="http://127.0.0.1:0", database="drafts")
        adapter.request = lambda *args: (_ for _ in ()).throw(BufferError("store_unavailable", "TerminusDB request could not be confirmed"))
        with self.assertRaisesRegex(BufferError, "could not be confirmed"):
            adapter.write([], "create_draft", "operation-1")

    def test_commitless_http_success_remains_unknown(self):
        adapter = TerminusDBDraftStore(base_url="http://127.0.0.1:0", database="drafts")
        adapter.request = lambda *args: (200, {}, b"{}")
        adapter.read_all = lambda: [{"@type":"Draft", "draft_id":"present"}]
        with self.assertRaisesRegex(BufferError, "exact commit could not be confirmed"):
            adapter.write([], "create_draft", "operation-1")


if __name__ == "__main__":
    unittest.main()
