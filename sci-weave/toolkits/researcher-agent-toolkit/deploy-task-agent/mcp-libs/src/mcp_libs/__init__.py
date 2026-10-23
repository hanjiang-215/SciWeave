"""Standard MCP resource catalogs and researcher-local extensions."""

from .registry import (
    MCPResource,
    MCPResourceError,
    MCPTool,
    MCPRegistry,
    load_mcp_registry,
    standard_mcp_resources,
)

__all__ = [
    "MCPResource", "MCPResourceError", "MCPTool", "MCPRegistry",
    "load_mcp_registry", "standard_mcp_resources",
]
