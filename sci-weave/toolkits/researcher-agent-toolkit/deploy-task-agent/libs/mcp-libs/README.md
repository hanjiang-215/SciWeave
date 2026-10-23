# MCP resource catalog

`mcp-libs` is a descriptor-only library: it documents tools and configuration, but never connects to a service. The standard resources are:

- `research-mapping`: read-only mapped entities and relations (`RESEARCH_MAPPING_MCP_URL`, `RESEARCH_MAPPING_MCP_TOKEN`).
- `research-wiki`: read-only cited background lookup (`RESEARCH_WIKI_MCP_URL`, `RESEARCH_WIKI_MCP_TOKEN`).
- `draft-buffer`: final draft persistence (`DRAFT_BUFFER_MCP_URL`, `DRAFT_BUFFER_MCP_TOKEN`).

Set `LOCAL_MCP_LIBS` to one or more local descriptor directories. Local resources take precedence over compatible same-name standard resources; conflicting or incompatible versions fail with stable errors.

Only the catalog is provided here. Domain MCP servers, credentials, and network calls remain outside this package; services must read addresses and tokens from environment configuration.
