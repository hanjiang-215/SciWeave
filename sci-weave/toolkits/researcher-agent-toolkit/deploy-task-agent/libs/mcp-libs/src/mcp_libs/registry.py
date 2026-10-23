"""Pure data registry for MCP resource descriptions; it never calls an MCP server."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class MCPResourceError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {detail}")


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    examples: tuple[Mapping[str, Any], ...]
    allowed: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class MCPResource:
    name: str
    version: str
    description: str
    tools: Mapping[str, MCPTool]
    environment: tuple[str, ...]
    source: str = "standard"


class MCPRegistry:
    def __init__(self, resources: tuple[MCPResource, ...]) -> None:
        self.resources = resources
        self._by_name = {item.name: item for item in resources}

    def get(self, name: str) -> MCPResource:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise MCPResourceError("unknown_resource", name) from exc

    def catalog(self, names: tuple[str, ...] | list[str] | None = None) -> dict[str, dict[str, Any]]:
        selected = self.resources if names is None else tuple(self.get(name) for name in names)
        return {item.name: {"version": item.version, "tools": {
            tool.name: {"description": tool.description, "input": dict(tool.input_schema),
                         "output": dict(tool.output_schema), "examples": list(tool.examples),
                         "allowed": list(tool.allowed), "failures": list(tool.failures)}
            for tool in item.tools.values()}, "environment": list(item.environment)} for item in selected}


def _tool(data: Mapping[str, Any]) -> MCPTool:
    return MCPTool(str(data["name"]), str(data.get("description", "")), data.get("input", {}), data.get("output", {}), tuple(data.get("examples", ())), tuple(data.get("allowed", ())), tuple(data.get("failures", ())))


def _resource(data: Mapping[str, Any], source: str) -> MCPResource:
    name, version = data.get("name"), data.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str):
        raise MCPResourceError("invalid_resource", "name and version are required")
    tools = tuple(_tool(item) for item in data.get("tools", ()))
    if len({item.name for item in tools}) != len(tools):
        raise MCPResourceError("invalid_resource", f"duplicate tool in {name}")
    return MCPResource(name, version, str(data.get("description", "")), {item.name: item for item in tools}, tuple(data.get("environment", ())), source)


def standard_mcp_resources() -> tuple[MCPResource, ...]:
    root = Path(__file__).parents[2] / "resources"
    return tuple(_resource(json.loads(path.read_text(encoding="utf-8")), "standard") for path in sorted(root.glob("*/resource.json")))


def _version(value: str) -> tuple[int, int, int]:
    try:
        parts = tuple(int(part) for part in value.split(".")[:3])
        return (parts + (0, 0, 0))[:3]
    except ValueError as exc:
        raise MCPResourceError("invalid_version", value) from exc


def load_mcp_registry(*, local_mcp_libs: str | Path | None = None) -> MCPRegistry:
    """Load standard resources and local JSON descriptors, with locals taking precedence."""
    standard = {item.name: item for item in standard_mcp_resources()}
    value = local_mcp_libs if local_mcp_libs is not None else os.getenv("LOCAL_MCP_LIBS", "")
    paths = [Path(item) for item in str(value).split(os.pathsep) if item]
    locals_: list[MCPResource] = []
    for directory in paths:
        for path in sorted(directory.glob("*.json")):
            locals_.append(_resource(json.loads(path.read_text(encoding="utf-8")), str(path)))
    grouped: dict[str, list[MCPResource]] = {}
    for item in locals_:
        grouped.setdefault(item.name, []).append(item)
    for name, items in grouped.items():
        if len(items) > 1:
            raise MCPResourceError("resource_conflict", name)
        item = items[0]
        if name in standard and not (1, 0, 0) <= _version(item.version) < (2, 0, 0):
            raise MCPResourceError("incompatible_version", f"{name} requires 1.x")
        standard[name] = item
    return MCPRegistry(tuple(standard[name] for name in sorted(standard)))
