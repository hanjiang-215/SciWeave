"""arXiv and Crossref literature search over stdio MCP.

Two tools only: ``search`` and ``get_abstract``. Neither needs a credential, so
the service starts without configuration and fails per call rather than at
startup.
"""

from __future__ import annotations

from literature_search.config import LiteratureConfig
from literature_search.tools import call
from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="literature-search",
    description="Search arXiv and Crossref for papers and read their abstracts.",
    version="0.1.0",
)


@server.tool(
    description=(
        "Search arXiv or Crossref. Returns a JSON array of "
        "{title, authors, published, id, abstract, url, source}. "
        "id is an arXiv id for arxiv and a DOI for crossref."
    )
)
def search(query: str, source: str = "arxiv", limit: int = 5) -> str:
    return call("search", {"query": query, "source": source, "limit": limit}, LiteratureConfig.from_env())


@server.tool(
    description=(
        "Read one paper by arXiv id or DOI. Returns JSON with "
        "{title, abstract, authors, published, url, license, source, id}. "
        "license is null when the source states none; it does not mean public domain."
    )
)
def get_abstract(id: str, source: str = "") -> str:
    return call("get_abstract", {"id": id, "source": source}, LiteratureConfig.from_env())


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
