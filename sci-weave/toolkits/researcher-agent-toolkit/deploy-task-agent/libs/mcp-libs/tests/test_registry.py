import json
import os
import tempfile
import unittest
from pathlib import Path

from mcp_libs import (
    MCPResourceError,
    load_mcp_registry,
    standard_mcp_resources,
)


class McpRegistryTests(unittest.TestCase):
    def test_standard_catalog_is_observable_and_complete(self) -> None:
        registry = load_mcp_registry()
        self.assertEqual(
            {resource.name for resource in registry.resources},
            {"research-mapping", "research-wiki", "draft-buffer"},
        )
        mapping = registry.get("research-mapping")
        self.assertIn("research_map_search", mapping.tools)
        self.assertIn("RESEARCH_MAPPING_MCP_URL", mapping.environment)
        self.assertTrue(mapping.tools["research_map_search"].input_schema)
        self.assertTrue(mapping.tools["research_map_search"].output_schema)
        self.assertTrue(mapping.tools["research_map_search"].examples)
        self.assertTrue(mapping.tools["research_map_search"].allowed)
        self.assertTrue(mapping.tools["research_map_search"].failures)

    def test_local_resource_extends_standard_and_overrides_by_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.json"
            path.write_text(json.dumps({
                "name": "research-mapping", "version": "1.1.0",
                "tools": [{"name": "research_map_search", "description": "local"}],
                "environment": ["RESEARCH_MAPPING_MCP_URL"],
            }), encoding="utf-8")
            registry = load_mcp_registry(local_mcp_libs=directory)
            self.assertEqual(registry.get("research-mapping").version, "1.1.0")
            self.assertEqual(registry.get("research-mapping").tools["research_map_search"].description, "local")

    def test_conflicts_and_incompatible_versions_are_stable_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for index in (1, 2):
                Path(directory, f"{index}.json").write_text(json.dumps({
                    "name": "local", "version": "2.0.0", "tools": []
                }), encoding="utf-8")
            with self.assertRaisesRegex(MCPResourceError, "resource_conflict"):
                load_mcp_registry(local_mcp_libs=directory)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "old.json").write_text(json.dumps({
                "name": "research-mapping", "version": "0.1.0", "tools": []
            }), encoding="utf-8")
            with self.assertRaisesRegex(MCPResourceError, "incompatible_version"):
                load_mcp_registry(local_mcp_libs=directory)

    def test_environment_variable_selects_local_directory_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "resource.json").write_text(json.dumps({
                "name": "private", "version": "1.0.0", "tools": []
            }), encoding="utf-8")
            old = os.environ.get("LOCAL_MCP_LIBS")
            os.environ["LOCAL_MCP_LIBS"] = directory
            try:
                self.assertIn("private", {item.name for item in load_mcp_registry().resources})
            finally:
                if old is None:
                    os.environ.pop("LOCAL_MCP_LIBS", None)
                else:
                    os.environ["LOCAL_MCP_LIBS"] = old


if __name__ == "__main__":
    unittest.main()
