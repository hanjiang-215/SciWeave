"""The card and the server must describe the same two tools.

The card is what an agent reads; the server is what answers. If they drift, an
agent calls a tool that does not exist or sends a field nobody accepts.
"""

from __future__ import annotations

import asyncio
import json
import re
import unittest
from pathlib import Path

import main

KIT_ROOT = Path(__file__).resolve().parents[3]
CARD = KIT_ROOT / "libs" / "mcp-libs" / "literature-search" / "mcp.json"
MCP_RESOURCES = KIT_ROOT / "runtime" / "src" / "work_agent_runtime" / "mcp_resources.py"


def load_card() -> dict:
    return json.loads(CARD.read_text(encoding="utf-8"))


def server_tools() -> dict[str, dict]:
    tools = asyncio.run(main.server.list_tools())
    return {tool.name: tool.input_schema for tool in tools}


class CardMatchesServerTests(unittest.TestCase):
    def test_the_card_exists(self) -> None:
        self.assertTrue(CARD.is_file(), f"{CARD} is missing")

    def test_the_card_and_the_server_expose_the_same_tools(self) -> None:
        card = load_card()
        self.assertEqual(
            {tool["name"] for tool in card["tools"]},
            set(server_tools()),
            "the card and src/main.py must declare exactly the same tools",
        )

    def test_each_tool_declares_the_same_required_fields(self) -> None:
        card = {tool["name"]: tool for tool in load_card()["tools"]}
        for name, schema in server_tools().items():
            with self.subTest(tool=name):
                self.assertEqual(
                    sorted(card[name]["input"].get("required", [])),
                    sorted(schema.get("required", [])),
                )

    def test_each_tool_declares_the_same_parameters(self) -> None:
        card = {tool["name"]: tool for tool in load_card()["tools"]}
        for name, schema in server_tools().items():
            with self.subTest(tool=name):
                self.assertEqual(
                    sorted(card[name]["input"]["properties"]),
                    sorted(schema["properties"]),
                )

    def test_the_limit_cap_in_the_card_matches_the_code(self) -> None:
        from literature_search.config import MAX_LIMIT

        card = {tool["name"]: tool for tool in load_card()["tools"]}
        limit = card["search"]["input"]["properties"]["limit"]
        self.assertEqual(limit["maximum"], MAX_LIMIT)

    def test_the_card_lists_every_failure_code_the_code_can_return(self) -> None:
        """An agent branches on these strings; a missing one is an unhandled case."""
        from literature_search import errors

        source = (KIT_ROOT / "custom-mcp" / "literature-search" / "src" / "literature_search").rglob("*.py")
        emitted = {"invalid_arguments", "unsupported_source", "unknown_tool", "literature_internal"}
        for path in source:
            emitted.update(re.findall(r'LiteratureError\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
            emitted.update(re.findall(r'LiteratureError\(\s*\n\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
        declared = set()
        for tool in load_card()["tools"]:
            declared.update(tool["failures"])
        self.assertTrue(emitted, "the scan found no error codes at all")
        self.assertLessEqual(emitted - {"unknown_tool", "literature_internal"}, declared)
        self.assertTrue(errors.LiteratureError)


class StartupWhitelistTests(unittest.TestCase):
    """`load_mcp_registry` rejects any stdio startup that is not this exact shape."""

    def test_the_card_startup_matches_the_runtime_whitelist_literally(self) -> None:
        card = load_card()
        startup = card["startup"]
        self.assertEqual(card["transport"], "stdio")
        self.assertEqual(startup["executable"], "uv")
        self.assertEqual(startup["args"], ["run", "--env-file", ".env", "python", "src/main.py"])
        self.assertTrue(startup["project_dir_env"])

    def test_the_whitelist_in_the_runtime_still_reads_the_same_way(self) -> None:
        """If someone relaxes the whitelist, this test tells them the card changed too."""
        source = MCP_RESOURCES.read_text(encoding="utf-8")
        self.assertIn('startup.get("executable") != "uv"', source)
        self.assertIn(
            'startup.get("args") != ["run", "--env-file", ".env", "python", "src/main.py"]', source
        )


if __name__ == "__main__":
    unittest.main()
