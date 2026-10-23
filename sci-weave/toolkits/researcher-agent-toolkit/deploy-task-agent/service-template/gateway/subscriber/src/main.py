from work_agent_runtime import FakeQueue, WorkAgentRuntime


queue = FakeQueue()
runtime = WorkAgentRuntime()
queue.subscribe(runtime.handle_message)


def main() -> None:
    print("gateway/subscriber template ready; configure the queue client here")


if __name__ == "__main__":
    main()
