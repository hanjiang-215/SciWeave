from work_agent_libs import ExecutionStore, FakeDraftBox, WorkerLease, run_one


def main() -> None:
    store = ExecutionStore()
    lease = WorkerLease()
    drafts = FakeDraftBox()
    result = run_one(store, lease, drafts, "task-node", "handoff-event", "researcher-task-agent")
    print(result)


if __name__ == "__main__":
    main()
