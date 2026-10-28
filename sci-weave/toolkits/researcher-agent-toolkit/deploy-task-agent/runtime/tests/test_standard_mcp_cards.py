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
    "email-service": {
        "send_notification", "get_notification_status",
    },
    # The source of truth is TOOL_DEFINITIONS in
    # sci-weave/centre-control/research-map/src/research_mapping/management.py
    # and .../research-wiki/src/llm_wiki/management.py. Both expectations had
    # drifted to 7 and 8 entries because they were updated together with the
    # cards instead of from the services (ai4-b4zb): adding a tool there means
    # adding it here and to libs/mcp-libs/<domain>/mcp.json.
    #
    # The two domain cards deliberately list FEWER tools than the services
    # define (ai4-tj83): `libs/mcp-libs/` is the task-agent capability surface,
    # not a mirror of the management MCP. Submitting, reviewing and formalizing
    # require the Owner-side capabilities and must not be advertised to a
    # researcher's Work Agent. Only the read/centre tools stay.
    "research-mapping": {
        "get_formal_mapping", "get_formal_mapping_at_revision", "list_candidates",
    },
    "research-wiki": {
        "get_formal_wiki", "list_wiki_candidates",
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
        self.assertIn("EMAIL_MCP_URL", catalog["email-service"]["environment"])
        self.assertIn("EMAIL_MCP_TOKEN", catalog["email-service"]["environment"])
        self.assertIn("RESEARCH_MAPPING_MCP_URL", catalog["research-mapping"]["environment"])
        self.assertIn("LLM_WIKI_MCP_URL", catalog["research-wiki"]["environment"])


if __name__ == "__main__":
    unittest.main()
