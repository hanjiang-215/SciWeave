from work_agent_libs import FakeDraftBox, ExecutionStore, WorkerLease

store = ExecutionStore()
lease = WorkerLease()
drafts = FakeDraftBox()


def main() -> None:
    print("worker template ready; configure the fast-agent invocation here")


if __name__ == "__main__":
    main()
