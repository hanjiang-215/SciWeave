"""Runtime validation tests for custom MCP service registration cards.

Covers ai4-cl3t acceptance: the runtime must parse registration cards, generate
MCP connection configs, and reject unknown transports, unsafe startup commands,
missing endpoints, duplicate tools, unknown resources, incompatible versions,
and conflicting local resources.
"""

import os
import tempfile
import unittest
from pathlib import Path

from work_agent_runtime import MCPResourceError, load_mcp_registry


def _write_card(directory: str, name: str, body: str) -> Path:
    path = Path(directory) / f"{name}.yaml"
    path.write_text(body, encoding="utf-8")
    return path


_STDIO_OK = (
    "name: svc\nversion: 1.0.0\ntransport: stdio\nstartup:\n"
    "  executable: uv\n  args: [run, --env-file, .env, python, src/main.py]\n"
    "  project_dir_env: SVC_PROJECT_DIR\n"
)


class MCPServiceCardValidationTests(unittest.TestCase):
    def test_accepts_safe_stdio_card(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(directory, "svc", _STDIO_OK)
            registry = load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(registry.catalog()["svc"]["transport"], "stdio")

    def test_rejects_unknown_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(directory, "svc", "name: svc\nversion: 1.0.0\ntransport: telepathy\n")
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "invalid_transport")

    def test_rejects_non_uv_stdio_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(
                directory,
                "svc",
                "name: svc\nversion: 1.0.0\ntransport: stdio\nstartup:\n"
                "  executable: python\n  args: [src/main.py]\n  project_dir_env: SVC_PROJECT_DIR\n",
            )
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "unsafe_startup")

    def test_rejects_arbitrary_stdio_args(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(
                directory,
                "svc",
                "name: svc\nversion: 1.0.0\ntransport: stdio\nstartup:\n"
                "  executable: uv\n  args: [run, --env-file, .env, python, -c, 'import os']\n"
                "  project_dir_env: SVC_PROJECT_DIR\n",
            )
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "unsafe_startup")

    def test_rejects_stdio_without_project_dir_env(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(
                directory,
                "svc",
                "name: svc\nversion: 1.0.0\ntransport: stdio\nstartup:\n"
                "  executable: uv\n  args: [run, --env-file, .env, python, src/main.py]\n",
            )
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "unsafe_startup")

    def test_rejects_http_card_with_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(
                directory,
                "svc",
                "name: svc\nversion: 1.0.0\ntransport: streamable-http\n"
                "endpoint: {url_env: SVC_URL}\nstartup:\n  executable: uv\n  args: [run]\n",
            )
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "unsafe_startup")

    def test_rejects_http_without_url_env(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(
                directory,
                "svc",
                "name: svc\nversion: 1.0.0\ntransport: streamable-http\nendpoint: {url: http://x}\n",
            )
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "invalid_endpoint")

    def test_rejects_duplicate_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(
                directory,
                "svc",
                "name: svc\nversion: 1.0.0\n"
                "tools:\n  - name: search\n  - name: search\n",
            )
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=directory)
            self.assertEqual(ctx.exception.code, "invalid_resource")

    def test_unknown_resource_raises_stable_code(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_card(directory, "svc", _STDIO_OK)
            registry = load_mcp_registry(standard_mcp_libs=directory)
            with self.assertRaises(MCPResourceError) as ctx:
                registry.get("no-such-service")
            self.assertEqual(ctx.exception.code, "unknown_resource")

    def test_rejects_incompatible_local_major_version(self):
        with tempfile.TemporaryDirectory() as standard, tempfile.TemporaryDirectory() as local:
            _write_card(standard, "svc", "name: svc\nversion: 1.0.0\n")
            _write_card(local, "svc", "name: svc\nversion: 2.0.0\n")
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(standard_mcp_libs=standard, local_mcp_libs=local)
            self.assertEqual(ctx.exception.code, "incompatible_version")

    def test_rejects_conflicting_local_resources(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            _write_card(first, "svc", "name: svc\nversion: 1.0.0\n")
            _write_card(second, "svc", "name: svc\nversion: 1.0.0\n")
            with self.assertRaises(MCPResourceError) as ctx:
                load_mcp_registry(local_mcp_libs=f"{first}{os.pathsep}{second}")
            self.assertEqual(ctx.exception.code, "resource_conflict")


if __name__ == "__main__":
    unittest.main()
