import unittest

from work_agent_runtime import FakeDraftBox, FakeQueue, WorkAgentRuntime, load_config


class RecordingDraftBox(FakeDraftBox):
    def __init__(self):
        self.calls = []

    def create_draft(self, target_id, payload):
        self.calls.append((target_id, payload))
        return f"draft-{len(self.calls)}"


class EndToEndTaskAgentTests(unittest.TestCase):
    def test_fake_upstream_subscriber_worker_multi_agent_draft(self):
        config = load_config(
            {
                "agents": {
                    "researcher": {"identity": "research", "instruction": "research", "model": "fake", "allowed_mcp_resources": [], "resources": []},
                    "reviewer": {"identity": "review", "instruction": "review", "model": "fake", "allowed_mcp_resources": [], "resources": []},
                    "writer": {"identity": "writer", "instruction": "write", "model": "fake", "allowed_mcp_resources": [], "resources": []},
                },
                "workflows": {
                    "main": {
                        "type": "Parallel",
                        "entry_agent": "researcher",
                        "sub_agents": ["researcher", "reviewer"],
                        "summarizer": "researcher",
                        "final_writer": "writer",
                    }
                },
            }
        )
        drafts = RecordingDraftBox()
        runtime = WorkAgentRuntime(drafts)
        queue = FakeQueue()
        calls = []

        def fake_agent(name, prompt, tools=None):
            calls.append((name, prompt))
            return "final answer" if name == "writer" else f"{name} result"

        # The queue callback is the subscriber-to-Worker seam; no real queue is used.
        queue.subscribe(
            lambda target_id, event_id: runtime.run_workflow(
                target_id, event_id, config, fake_agent, "main", "upstream question"
            )
        )
        execution = queue.deliver("task-node", "upstream-1")

        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.draft_id, "draft-1")
        self.assertEqual(len({execution.draft_id}), 1)
        self.assertEqual(len(drafts.calls), 1)
        self.assertEqual(drafts.calls[0][0], "task-node")
        self.assertEqual({name for name, _ in calls}, {"researcher", "reviewer", "writer"})
        self.assertEqual(execution.error_code, None)


if __name__ == "__main__":
    unittest.main()
