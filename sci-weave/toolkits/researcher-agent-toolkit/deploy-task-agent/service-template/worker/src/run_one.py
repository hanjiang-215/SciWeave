from work_agent_runtime import BufferMCPDraftWriter, WorkAgentRuntime


def build_runtime() -> WorkAgentRuntime:
    import os

    runtime = WorkAgentRuntime()
    draft_url = os.environ.get("DRAFT_BUFFER_MCP_URL", "").strip()
    draft_token = os.environ.get("DRAFT_BUFFER_MCP_TOKEN", "").strip()
    if draft_url and draft_token:
        namespace = os.environ.get("SCIWEAVE_DRAFT_NAMESPACE", "mapping").strip() or "mapping"
        submitter_id = os.environ.get("SCIWEAVE_AGENT_ID", "").strip() or "researcher-task-agent"
        runtime.drafts = BufferMCPDraftWriter(
            endpoint=draft_url,
            token=draft_token,
            namespace=namespace,
            submitter_id=submitter_id,
        )
    return runtime


def main() -> None:
    runtime = build_runtime()
    result = runtime.run_one("task-node", "handoff-event", "researcher-task-agent")
    print(result)


if __name__ == "__main__":
    main()