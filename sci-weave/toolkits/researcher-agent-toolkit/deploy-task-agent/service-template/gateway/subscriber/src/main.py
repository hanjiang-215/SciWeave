from work_agent_libs import FakeQueue, ExecutionStore, FakeDraftBox, WorkerLease

queue = FakeQueue()
store = ExecutionStore()
lease = WorkerLease()
drafts = FakeDraftBox()


def main() -> None:
    print("gateway/subscriber template ready; configure the queue client here")


if __name__ == "__main__":
    main()
