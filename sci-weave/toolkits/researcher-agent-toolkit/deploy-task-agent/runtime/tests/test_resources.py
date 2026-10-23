"""Runtime resource loading tests for configuration-only libraries."""
import tempfile
import unittest
from pathlib import Path
from work_agent_runtime import load_agent_registry, load_mcp_registry

class ResourceTests(unittest.TestCase):
    def test_loads_agent_resources_from_yaml_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.yaml"
            path.write_text("name: local.prompt\nversion: 1.0.0\nkind: prompt\nvalue: answer\n", encoding="utf-8")
            registry = load_agent_registry(standard_path=directory)
            self.assertEqual(registry.resolve("local.prompt@1").value, "answer")

    def test_loads_mcp_resources_from_nested_resource_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory) / "service" / "mcp.yaml"
            resource.parent.mkdir()
            resource.write_text("name: local-mcp\nversion: 1.0.0\ntools: []\n", encoding="utf-8")
            registry = load_mcp_registry(standard_mcp_libs=directory)
            self.assertIn("local-mcp", registry.catalog())

if __name__ == "__main__":
    unittest.main()
