"""MCP resource descriptors loaded by the Work Agent runtime."""
from __future__ import annotations
import json, os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import yaml

class MCPResourceError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"[{code}] {detail}")
@dataclass(frozen=True)
class MCPTool:
    name: str; description: str; input_schema: Mapping[str, Any]; output_schema: Mapping[str, Any]
    examples: tuple[Mapping[str, Any], ...]; allowed: tuple[str, ...]; failures: tuple[str, ...]
@dataclass(frozen=True)
class MCPResource:
    name: str; version: str; description: str; tools: Mapping[str, MCPTool]; environment: tuple[str, ...]
    source: str = "standard"; transport: str = "streamable-http"; startup: Mapping[str, Any] = None; endpoint: Mapping[str, Any] = None
class MCPRegistry:
    def __init__(self, resources: tuple[MCPResource, ...]):
        self.resources = resources; self._by_name = {item.name: item for item in resources}
    def get(self, name):
        try: return self._by_name[name]
        except KeyError as exc: raise MCPResourceError("unknown_resource", name) from exc
    def catalog(self, names=None):
        selected = self.resources if names is None else tuple(self.get(name) for name in names)
        return {item.name: {"version": item.version, "transport": item.transport, "startup": dict(item.startup or {}), "endpoint": dict(item.endpoint or {}), "environment": list(item.environment), "tools": {tool.name: {"description": tool.description, "input": dict(tool.input_schema), "output": dict(tool.output_schema), "examples": list(tool.examples), "allowed": list(tool.allowed), "failures": list(tool.failures)} for tool in item.tools.values()}} for item in selected}
def _tool(data):
    return MCPTool(str(data["name"]), str(data.get("description", "")), data.get("input", {}), data.get("output", {}), tuple(data.get("examples", ())), tuple(data.get("allowed", data.get("access", ()))), tuple(data.get("failures", ())))
def _resource(data, source):
    name, version = data.get("name"), data.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str): raise MCPResourceError("invalid_resource", "name and version are required")
    transport = str(data.get("transport", "streamable-http")); startup = data.get("startup") or {}; endpoint = data.get("endpoint") or {}
    if transport not in {"stdio", "streamable-http"}: raise MCPResourceError("invalid_transport", transport)
    if transport == "stdio" and startup and (startup.get("executable") != "uv" or startup.get("args") != ["run", "--env-file", ".env", "python", "src/main.py"] or not startup.get("project_dir_env")): raise MCPResourceError("unsafe_startup", name)
    if transport == "streamable-http" and "transport" in data and not isinstance(endpoint.get("url_env"), str): raise MCPResourceError("invalid_endpoint", name)
    if startup and transport != "stdio": raise MCPResourceError("unsafe_startup", name)
    tools = tuple(_tool(item) for item in data.get("tools", ()))
    if len({tool.name for tool in tools}) != len(tools): raise MCPResourceError("invalid_resource", f"duplicate tool in {name}")
    return MCPResource(name, version, str(data.get("description", "")), {tool.name: tool for tool in tools}, tuple(data.get("environment", ())), source, transport, startup, endpoint)
def _load(path, source):
    result=[]
    for item in sorted((*path.rglob("*.json"), *path.rglob("*.yaml"), *path.rglob("*.yml"))):
        try:
            text=item.read_text(encoding="utf-8"); data=json.loads(text) if item.suffix == ".json" else yaml.safe_load(text)
            if not isinstance(data, Mapping): raise MCPResourceError("invalid_resource", str(item))
            result.append(_resource(data, source))
        except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc: raise MCPResourceError("invalid_resource", str(item)) from exc
    return result
def _optional_path(name):
    value = os.getenv(name, "")
    return Path(value) if value else None

def load_mcp_registry(*, standard_mcp_libs=None, local_mcp_libs=None):
    standard_path=Path(standard_mcp_libs) if standard_mcp_libs is not None else _optional_path("MCP_LIBS_PATH")
    standard_items = _load(standard_path, "standard") if standard_path and standard_path.exists() else []
    standard: dict[str, MCPResource] = {}
    for item in standard_items:
        key = (item.name, item.version)
        if any(existing.name == item.name and existing.version == item.version for existing in standard.values()):
            raise MCPResourceError("resource_conflict", item.name)
        standard[item.name] = item
    value=local_mcp_libs if local_mcp_libs is not None else os.getenv("LOCAL_MCP_LIBS", "")
    seen_global: set[str] = set()
    for raw in str(value).split(os.pathsep):
        if not raw:
            continue
        local_items = _load(Path(raw), "local")
        for item in local_items:
            if item.name in seen_global:
                raise MCPResourceError("resource_conflict", item.name)
            seen_global.add(item.name)
            if item.name in standard and not (1 <= int(item.version.split(".")[0]) < 2):
                raise MCPResourceError("incompatible_version", item.name)
            standard[item.name] = item
    return MCPRegistry(tuple(standard[name] for name in sorted(standard)))
