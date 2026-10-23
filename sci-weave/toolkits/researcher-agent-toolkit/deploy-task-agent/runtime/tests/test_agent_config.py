import json
import unittest

from work_agent_runtime import ConfigError, load_config


AGENTS = {
    "router": {"identity": "Routes research", "instruction": "Route", "model": "fake", "allowed_mcp_resources": ["search"], "resources": ["routing"]},
    "searcher": {"identity": "Searches", "instruction": "Search", "model": "fake", "allowed_mcp_resources": ["search"], "resources": ["research"]},
    "writer": {"identity": "Writes", "instruction": "Write", "model": "fake", "allowed_mcp_resources": ["draft"], "resources": ["formatting"]},
}


class AgentConfigTests(unittest.TestCase):
    def test_loads_stable_model_from_mapping_and_json(self) -> None:
        raw = {"agents": AGENTS, "workflows": {"main": {"type": "Router", "entry_agent": "router", "sub_agents": ["searcher"], "summarizer": "router", "final_writer": "writer"}}}
        config = load_config(raw, known_mcp_resources={"search", "draft"}, known_agent_resources={"routing", "research", "formatting"}, mcp_catalog={"search": {"tools": ["search"]}})
        restored = load_config(json.dumps(raw), known_mcp_resources={"search", "draft"}, known_agent_resources={"routing", "research", "formatting"}, mcp_catalog={"search": {"tools": ["search"]}})
        self.assertEqual(config, restored)
        self.assertEqual(config.mcp_catalog["search"]["tools"], ["search"])
        self.assertEqual(config.workflows["main"].workflow_type, "Router")
        self.assertEqual(config.agents["writer"].allowed_mcp_resources, ("draft",))

    def test_all_supported_workflow_types_are_valid(self) -> None:
        for workflow_type in ("Router", "Orchestrator", "Parallel", "Agents as Tools"):
            raw = {"agents": AGENTS, "workflows": {"main": {"type": workflow_type, "entry_agent": "router", "sub_agents": ["searcher"], "summarizer": "router", "final_writer": "writer"}}}
            load_config(raw, known_mcp_resources={"search", "draft"}, known_agent_resources={"routing", "research", "formatting"})

    def test_rejects_missing_required_fields_unknown_references_and_type(self) -> None:
        base = {"agents": AGENTS, "workflows": {"main": {"type": "Router", "entry_agent": "router", "sub_agents": ["searcher"], "summarizer": "router", "final_writer": "writer"}}}
        cases = (("missing_entry_agent", {"entry_agent": None}), ("missing_final_writer", {"final_writer": None}), ("missing_sub_agents", {"sub_agents": []}), ("unknown_workflow_type", {"type": "Unknown"}), ("unknown_agent", {"entry_agent": "ghost"}))
        for code, changes in cases:
            raw = json.loads(json.dumps(base))
            raw["workflows"]["main"].update(changes)
            with self.subTest(code=code):
                with self.assertRaisesRegex(ConfigError, code):
                    load_config(raw, known_mcp_resources={"search", "draft"}, known_agent_resources={"routing", "research", "formatting"})

    def test_rejects_unknown_resources_and_cycles(self) -> None:
        raw = {"agents": {**AGENTS, "searcher": {**AGENTS["searcher"], "allowed_mcp_resources": ["missing"]}}, "workflows": {"main": {"type": "Parallel", "entry_agent": "router", "sub_agents": ["searcher"], "summarizer": "router", "final_writer": "writer"}}}
        with self.assertRaisesRegex(ConfigError, "unknown_mcp_resource"):
            load_config(raw, known_mcp_resources={"search", "draft"}, known_agent_resources={"routing", "research", "formatting"})
        cyclic = {"agents": {**AGENTS, "router": {**AGENTS["router"], "tools": ["writer"]}, "writer": {**AGENTS["writer"], "tools": ["router"]}}, "workflows": {"main": {"type": "Agents as Tools", "entry_agent": "router", "sub_agents": ["writer"], "summarizer": "router", "final_writer": "writer"}}}
        with self.assertRaisesRegex(ConfigError, "cyclic_reference"):
            load_config(cyclic, known_mcp_resources={"search", "draft"}, known_agent_resources={"routing", "research", "formatting"})


if __name__ == "__main__":
    unittest.main()
