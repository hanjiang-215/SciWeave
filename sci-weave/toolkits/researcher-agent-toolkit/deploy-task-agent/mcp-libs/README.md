# MCP resource catalog

`mcp-libs` is a descriptor-only library: it documents tools and configuration, but never connects to a service. The standard resources are:

- `research-mapping`: read-only mapped entities and relations (`RESEARCH_MAPPING_MCP_URL`, `RESEARCH_MAPPING_MCP_TOKEN`).
- `llm-wiki`: read-only cited background lookup (`LLM_WIKI_MCP_URL`, `LLM_WIKI_MCP_TOKEN`).
- `draft-box`: final draft persistence (`DRAFT_BUFFER_MCP_URL`, `DRAFT_BUFFER_MCP_TOKEN`).

A resource descriptor is JSON with a stable `name`, semantic `version`, `tools`, and environment variable names. Set `LOCAL_MCP_LIBS` to one or more local descriptor directories (the platform path separator separates directories). Local resources take precedence over same-name standard resources when they are compatible with version 1.x. Multiple local descriptors with the same name fail with `[resource_conflict]`; an incompatible standard override fails with `[incompatible_version]`.

Example:

```python
from mcp_libs import load_mcp_registry
registry = load_mcp_registry()
agent_catalog = registry.catalog(("research-mapping", "draft-box"))
```

Only the catalog is provided here. Domain MCP servers, credentials, and network calls remain outside this package; services must read their addresses and tokens from environment configuration.
