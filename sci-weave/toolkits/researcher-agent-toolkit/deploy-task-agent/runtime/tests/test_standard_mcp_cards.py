"""Verify the standard MCP cards load and match the real service tool surface."""

import unittest
from pathlib import Path

from work_agent_runtime import load_mcp_registry

MCP_LIBS = Path(__file__).resolve().parents[2] / "libs" / "mcp-libs"

EXPECTED = {
    "draft-buffer": {
        "create_draft", "update_draft", "submit_draft", "list_drafts",
        "read_draft", "review_draft", "mark_promoted",
    },
    "research-mapping": {
        "get_formal_mapping", "list_candidates", "submit_candidate",
        "preview_candidate", "record_review", "formalize_candidate",
        "reconcile_formalization",
    },
    "research-wiki": {
        "get_formal_wiki", "list_wiki_candidates", "submit_wiki_candidate",
        "preview_wiki_review", "create_wiki_merge_request", "decide_wiki_review",
        "formalize_wiki", "reconcile_wiki_formalization",
    },
}


class StandardMCPCardTests(unittest.TestCase):
    def test_standard_cards_load_and_expose_real_tool_surface(self):
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        catalog = registry.catalog()
        for name, expected_tools in EXPECTED.items():
            self.assertIn(name, catalog)
            resource = catalog[name]
            self.assertEqual(resource["transport"], "streamable-http")
            self.assertIn("url_env", resource["endpoint"])
            self.assertEqual(set(resource["tools"]), expected_tools)
            for tool_name, tool in resource["tools"].items():
                self.assertTrue(tool["description"], tool_name)
                self.assertIn("type", tool["input"], tool_name)

    def test_standard_cards_declare_connection_environment(self):
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        catalog = registry.catalog()
        self.assertIn("DRAFT_BUFFER_MCP_URL", catalog["draft-buffer"]["environment"])
        self.assertIn("RESEARCH_MAPPING_MCP_URL", catalog["research-mapping"]["environment"])
        self.assertIn("LLM_WIKI_MCP_URL", catalog["research-wiki"]["environment"])


if __name__ == "__main__":
    unittest.main()
