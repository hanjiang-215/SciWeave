"""MCP card translation tests (ai4-349h).

The seam is ``load_cards`` + ``fast_agent_servers`` + ``render_fast_agent_config``:
a directory of cards and a mapping of environment variables go in, a config file
body comes out. Nothing here asserts how the card JSON is walked.
"""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

from task_agent_worker.mcp_servers import (
    MCPServerConfigError,
    fast_agent_servers,
    load_cards,
    render_fast_agent_config,
)


def _card(directory: Path, folder_name: str, **overrides: object) -> Path:
    payload = {
        "name": folder_name,
        "version": "1.0.0",
        "description": f"{folder_name} card",
        "transport": "streamable-http",
        "endpoint": {"url_env": f"{folder_name.upper().replace('-', '_')}_URL"},
        "environment": [f"{folder_name.upper().replace('-', '_')}_URL"],
        "tools": [{"name": "read", "description": "read"}, {"name": "write", "description": "write"}],
    }
    payload.update(overrides)
    folder = directory / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "mcp.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class CardLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_loads_every_card_by_its_declared_name(self) -> None:
        _card(self.root, "research-mapping")
        _card(self.root, "email-service")
        cards = load_cards(self.root)
        self.assertEqual(sorted(cards), ["email-service", "research-mapping"])
        self.assertEqual(cards["research-mapping"].tools, ("read", "write"))

    def test_a_missing_directory_is_an_error(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            load_cards(self.root / "nowhere")
        self.assertEqual(caught.exception.code, "cards_missing")

    def test_a_directory_without_cards_is_an_error(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            load_cards(self.root)
        self.assertEqual(caught.exception.code, "cards_missing")

    def test_a_card_whose_name_disagrees_with_its_folder_is_refused(self) -> None:
        # The folder name is how `allowed_mcp_resources` reaches a card, so a
        # mismatch makes one of the two spellings silently unreachable.
        _card(self.root, "research-mapping", name="mapping")
        with self.assertRaises(MCPServerConfigError) as caught:
            load_cards(self.root)
        self.assertEqual(caught.exception.code, "card_name_mismatch")

    def test_an_unreadable_card_is_refused(self) -> None:
        folder = self.root / "broken"
        folder.mkdir()
        (folder / "mcp.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(MCPServerConfigError) as caught:
            load_cards(self.root)
        self.assertEqual(caught.exception.code, "card_invalid")


class ServerTranslationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _card(self.root, "research-mapping")
        self.cards = load_cards(self.root)

    def test_streamable_http_becomes_http_with_the_url_value(self) -> None:
        servers = fast_agent_servers(["research-mapping"], self.cards, {"RESEARCH_MAPPING_URL": "https://mcp.invalid/mcp"})
        self.assertEqual(
            servers, {"research-mapping": {"transport": "http", "url": "https://mcp.invalid/mcp"}}
        )

    def test_a_missing_url_variable_names_both_the_variable_and_the_card(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            fast_agent_servers(["research-mapping"], self.cards, {})
        self.assertEqual(caught.exception.code, "missing_environment")
        self.assertEqual(caught.exception.server, "research-mapping")
        self.assertIn("RESEARCH_MAPPING_URL", caught.exception.detail)

    def test_an_undeclared_server_is_refused_not_skipped(self) -> None:
        with self.assertRaises(MCPServerConfigError) as caught:
            fast_agent_servers(["ghost"], self.cards, {})
        self.assertEqual(caught.exception.code, "unknown_server")
        self.assertIn("research-mapping", caught.exception.detail)

    def test_only_the_named_servers_are_emitted(self) -> None:
        _card(self.root, "email-service")
        cards = load_cards(self.root)
        environ = {"RESEARCH_MAPPING_URL": "https://m.invalid/mcp", "EMAIL_SERVICE_URL": "https://e.invalid/mcp"}
        servers = fast_agent_servers(["email-service"], cards, environ)
        self.assertEqual(sorted(servers), ["email-service"])

    def test_a_stdio_card_translates_to_command_and_cwd(self) -> None:
        _card(
            self.root,
            "stdio-service",
            transport="stdio",
            endpoint=None,
            startup={"executable": "uv", "args": ["run", "src/main.py"], "project_dir_env": "STDIO_PROJECT_DIR"},
        )
        cards = load_cards(self.root)
        servers = fast_agent_servers(["stdio-service"], cards, {"STDIO_PROJECT_DIR": "/tmp/project"})
        self.assertEqual(
            servers["stdio-service"],
            {
                "transport": "stdio",
                "command": "uv",
                "args": ["run", "src/main.py"],
                "cwd": "/tmp/project",
            },
        )

    def test_an_unsupported_transport_is_refused(self) -> None:
        _card(self.root, "odd", transport="websocket")
        cards = load_cards(self.root)
        with self.assertRaises(MCPServerConfigError) as caught:
            fast_agent_servers(["odd"], cards, {"ODD_URL": "https://odd.invalid/mcp"})
        self.assertEqual(caught.exception.code, "unsupported_transport")


class RenderTests(unittest.TestCase):
    def test_no_servers_still_emits_the_two_settings_and_no_empty_mcp_block(self) -> None:
        # An `mcp:` key with no children is valid YAML but reads as a mistake.
        self.assertEqual(
            render_fast_agent_config({}), "compaction:\n  auto: false\nsession_history: true\n"
        )

    def test_the_rendered_text_is_valid_yaml_fast_agent_can_read(self) -> None:
        body = render_fast_agent_config(
            {
                "research-mapping": {"transport": "http", "url": "https://m.invalid/mcp"},
                "email-service": {"transport": "http", "url": "https://e.invalid/mcp"},
            }
        )
        document = yaml.safe_load(body)
        self.assertFalse(document["compaction"]["auto"])
        self.assertTrue(document["session_history"])
        self.assertEqual(
            document["mcp"]["servers"]["research-mapping"],
            {"transport": "http", "url": "https://m.invalid/mcp"},
        )
        self.assertEqual(sorted(document["mcp"]["servers"]), ["email-service", "research-mapping"])

    def test_a_url_needing_quotes_is_quoted(self) -> None:
        body = render_fast_agent_config(
            {"svc": {"transport": "http", "url": "https://host.invalid/mcp#fragment"}}
        )
        document = yaml.safe_load(body)
        self.assertEqual(document["mcp"]["servers"]["svc"]["url"], "https://host.invalid/mcp#fragment")


if __name__ == "__main__":
    unittest.main()
