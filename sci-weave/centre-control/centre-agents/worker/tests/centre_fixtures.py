"""A minimal, self-consistent ``centre-agents`` tree for tests (ai4-349h).

Both `test_assembly.py` and `test_runtime.py` need the same three directories —
definitions, MCP cards, rules — and a tree that disagrees with itself between the
two files would let a wiring bug pass. It lives here rather than in either test
module so neither has to import the other, which behaves differently under
``pytest`` and ``unittest discover``.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

CARD_TOOLS = {
    "research-mapping": ("get_formal_mapping", "list_reviewable_candidates", "append_prereview_log"),
    "research-wiki": ("get_formal_wiki", "list_reviewable_wiki_candidates", "append_prereview_log"),
    "email-service": ("send_notification",),
}

URL_VARIABLES = {
    "research-mapping": "RESEARCH_MAPPING_MCP_URL",
    "research-wiki": "LLM_WIKI_MCP_URL",
    "email-service": "EMAIL_MCP_URL",
}

ENVIRON = {
    "RESEARCH_MAPPING_MCP_URL": "https://mapping.invalid/mcp",
    "LLM_WIKI_MCP_URL": "https://wiki.invalid/mcp",
    "EMAIL_MCP_URL": "https://email.invalid/mcp",
}

DEFINITION = textwrap.dedent(
    """\
    version: 1.0.0
    agents:
      step-read:
        identity: reader
        instruction: read the snapshot, then stop
        model: configure-in-your-own-environment
        allowed_mcp_resources: [research-mapping, research-wiki]
        allowed_tools:
          research-mapping: [list_reviewable_candidates]
          research-wiki: [list_reviewable_wiki_candidates]
        resources: []
      step-write:
        identity: writer
        instruction: append the verdict for rule set {{rule_set_version}}
        model: deepseek-chat
        allowed_mcp_resources: [research-mapping, email-service]
        allowed_tools:
          research-mapping: [append_prereview_log]
          email-service: [send_notification]
        resources: []
    workflows:
      centre-prereview:
        type: Chain
        sequence: [step-read, step-write]
    """
)


def build_tree(root: Path, *, definition: str = DEFINITION, cards: dict | None = None) -> Path:
    """Write ``definitions/``, ``libs/mcp-libs/`` and ``rules/`` under ``root``."""
    definitions = root / "definitions"
    definitions.mkdir(parents=True, exist_ok=True)
    (definitions / "centre-prereview.yaml").write_text(definition, encoding="utf-8")
    (definitions / "schema.yaml").write_text("# documentation only\n", encoding="utf-8")
    libs = root / "libs" / "mcp-libs"
    for name, tools in (cards if cards is not None else CARD_TOOLS).items():
        folder = libs / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mcp.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": "1.0.0",
                    "transport": "streamable-http",
                    "endpoint": {"url_env": URL_VARIABLES[name]},
                    "environment": [URL_VARIABLES[name]],
                    "tools": [{"name": tool, "description": tool} for tool in tools],
                }
            ),
            encoding="utf-8",
        )
    rules = root / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "1.0.0.json").write_text(
        json.dumps({"version": "1.0.0", "checks": ["权限范围", "基准版本", "冲突", "影响范围"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root
