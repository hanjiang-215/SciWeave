from work_agent_libs import ExecutionStore, FakeDraftBox, WorkerLease

# The real service template only wires configured libraries; it does not reimplement state.
store = ExecutionStore()
lease = WorkerLease()
drafts = FakeDraftBox()


def main() -> None:
    print("gateway/mcp template ready; configure the MCP transport here")


if __name__ == "__main__":
    main()
