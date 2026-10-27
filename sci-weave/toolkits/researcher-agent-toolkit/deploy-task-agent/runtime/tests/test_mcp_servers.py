"""MCP cards -> `mcp.servers` (ai4-x0ay).

Before this, `_write_fast_agent_config()` emitted only `compaction` and
`session_history`, so every agent ran with **no MCP tools**: the cards in
`libs/mcp-libs/` described tools nothing could call. These tests pin the
translation, the per-agent scoping, and the refusal to skip a server whose
environment variable is missing.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from work_agent_runtime.mcp_servers import (
    MCPServerConfigError,
    fast_agent_servers,
    render_fast_agent_config,
    server_spec,
)

KIT_ROOT = Path(__file__).resolve().parents[2]
MCP_LIBS = KIT_ROOT / "libs" / "mcp-libs"

_HTTP_CARD = {
    "name": "draft-buffer",
    "transport": "streamable-http",
    "endpoint": {"url_env": "DRAFT_BUFFER_MCP_URL"},
    "environment": ["DRAFT_BUFFER_MCP_URL", "DRAFT_BUFFER_MCP_TOKEN"],
}
_STDIO_CARD = {
    "name": "literature-search",
    "transport": "stdio",
    "startup": {
        "executable": "uv",
        "args": ["run", "--env-file", ".env", "python", "src/main.py"],
        "project_dir_env": "LITERATURE_MCP_PROJECT_DIR",
    },
}


class TransportTranslationTests(unittest.TestCase):
    def test_a_streamable_http_card_becomes_fast_agents_http_transport(self) -> None:
        """fast-agent's literal type is `stdio`/`sse`/`http`, not `streamable-http`."""
        spec = server_spec("draft-buffer", _HTTP_CARD, {"DRAFT_BUFFER_MCP_URL": "https://b.invalid/mcp"})
        self.assertEqual(spec.transport, "http")
        self.assertEqual(spec.url, "https://b.invalid/mcp")

    def test_a_stdio_card_becomes_a_command_with_a_cwd(self) -> None:
        spec = server_spec("literature-search", _STDIO_CARD, {"LITERATURE_MCP_PROJECT_DIR": "/opt/lit"})
        self.assertEqual(spec.transport, "stdio")
        self.assertEqual(spec.command, "uv")
        self.assertEqual(spec.args, ("run", "--env-file", ".env", "python", "src/main.py"))
        self.assertEqual(spec.cwd, "/opt/lit")

    def test_an_unknown_transport_is_refused(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            server_spec("x", {"transport": "websocket"}, {})
        self.assertEqual(caught.exception.code, "unsupported_transport")


class MissingEnvironmentTests(unittest.TestCase):
    """A silently dropped server is an agent quietly missing a tool."""

    def test_a_missing_url_variable_names_the_variable(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            server_spec("draft-buffer", _HTTP_CARD, {})
        self.assertEqual(caught.exception.code, "missing_environment")
        self.assertIn("DRAFT_BUFFER_MCP_URL", str(caught.exception))

    def test_a_blank_url_variable_counts_as_missing(self) -> None:
        with self.assertRaises(MCPServerConfigError):
            server_spec("draft-buffer", _HTTP_CARD, {"DRAFT_BUFFER_MCP_URL": "   "})

    def test_a_missing_project_directory_variable_is_refused(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            server_spec("literature-search", _STDIO_CARD, {})
        self.assertIn("LITERATURE_MCP_PROJECT_DIR", str(caught.exception))

    def test_a_remote_card_without_url_env_is_refused_not_defaulted(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            server_spec("x", {"transport": "streamable-http", "endpoint": {}}, {})
        self.assertEqual(caught.exception.code, "invalid_endpoint")


class ScopingTests(unittest.TestCase):
    """Only the cards an agent declares; a reader must not get `create_draft`."""

    def setUp(self) -> None:
        self.catalog = {
            "draft-buffer": {"transport": "streamable-http", "endpoint": {"url_env": "DRAFT_BUFFER_MCP_URL"}},
            "research-wiki": {"transport": "streamable-http", "endpoint": {"url_env": "LLM_WIKI_MCP_URL"}},
        }
        self.env = {
            "DRAFT_BUFFER_MCP_URL": "https://b.invalid/mcp",
            "LLM_WIKI_MCP_URL": "https://w.invalid/mcp",
        }

    def test_only_the_declared_servers_appear(self) -> None:
        servers = fast_agent_servers(("research-wiki",), self.catalog, self.env)
        self.assertEqual(list(servers), ["research-wiki"])
        self.assertNotIn("draft-buffer", servers)

    def test_no_declared_resources_means_no_servers_at_all(self) -> None:
        self.assertEqual(fast_agent_servers((), self.catalog, self.env), {})

    def test_an_undeclared_name_is_refused(self) -> None:
        with self.assertRaises(MCPServerConfigError):
            fast_agent_servers(("sciencepal",), self.catalog, self.env)


class RenderedConfigTests(unittest.TestCase):
    def test_an_agent_with_no_servers_still_gets_the_two_settings(self) -> None:
        text = render_fast_agent_config({})
        self.assertIn("compaction:", text)
        self.assertIn("auto: false", text)
        self.assertIn("session_history: true", text)
        self.assertNotIn("mcp:", text)

    def test_the_rendered_yaml_parses_and_keeps_the_translation(self) -> None:
        servers = fast_agent_servers(
            ("draft-buffer",),
            {"draft-buffer": {"transport": "streamable-http", "endpoint": {"url_env": "DRAFT_BUFFER_MCP_URL"}}},
            {"DRAFT_BUFFER_MCP_URL": "https://b.invalid/mcp"},
        )
        document = yaml.safe_load(render_fast_agent_config(servers))
        self.assertEqual(document["compaction"], {"auto": False})
        self.assertTrue(document["session_history"])
        self.assertEqual(
            document["mcp"]["servers"]["draft-buffer"],
            {"transport": "http", "url": "https://b.invalid/mcp"},
        )

    def test_a_stdio_server_renders_command_args_and_cwd(self) -> None:
        servers = fast_agent_servers(
            ("literature-search",),
            {"literature-search": _STDIO_CARD},
            {"LITERATURE_MCP_PROJECT_DIR": "/opt/lit"},
        )
        document = yaml.safe_load(render_fast_agent_config(servers))
        self.assertEqual(
            document["mcp"]["servers"]["literature-search"],
            {
                "transport": "stdio",
                "command": "uv",
                "args": ["run", "--env-file", ".env", "python", "src/main.py"],
                "cwd": "/opt/lit",
            },
        )

    def test_a_value_that_needs_quoting_survives_the_round_trip(self) -> None:
        servers = {"x": {"transport": "http", "url": "https://h.invalid/a#frag"}}
        document = yaml.safe_load(render_fast_agent_config(servers))
        self.assertEqual(document["mcp"]["servers"]["x"]["url"], "https://h.invalid/a#frag")


class ShippedCardsTests(unittest.TestCase):
    """The real cards in `libs/mcp-libs/`, not hand-written fixtures."""

    def _card(self, name: str) -> dict:
        import json

        return json.loads((MCP_LIBS / name / "mcp.json").read_text(encoding="utf-8"))

    def test_every_shipped_card_translates_given_its_environment(self) -> None:
        env = {
            "DRAFT_BUFFER_MCP_URL": "https://b.invalid/mcp",
            "EMAIL_MCP_URL": "https://e.invalid/mcp",
            "RESEARCH_MAPPING_MCP_URL": "https://m.invalid/mcp",
            "LLM_WIKI_MCP_URL": "https://w.invalid/mcp",
            "LITERATURE_MCP_PROJECT_DIR": "/opt/lit",
            "SCIENCEPAL_BRIDGE_DIR": "/opt/sp",
        }
        for directory in sorted(MCP_LIBS.iterdir()):
            card_path = directory / "mcp.json"
            if not card_path.is_file():
                continue
            with self.subTest(card=directory.name):
                card = self._card(directory.name)
                spec = server_spec(card["name"], card, env)
                self.assertIn(spec.transport, {"http", "stdio"})
                self.assertTrue(spec.url or spec.command, "every server needs a target")

    def test_the_sciencepal_card_renders_with_its_project_directory(self) -> None:
        card = self._card("sciencepal")
        spec = server_spec("sciencepal", card, {"SCIENCEPAL_BRIDGE_DIR": "/opt/sp"})
        self.assertEqual((spec.transport, spec.command, spec.cwd), ("stdio", "uv", "/opt/sp"))


if __name__ == "__main__":
    unittest.main()
