from work_agent_runtime import WorkAgentRuntime


runtime = WorkAgentRuntime()


def main() -> None:
    result = runtime.run_one("task-node", "handoff-event", "researcher-task-agent")
    print(result)


if __name__ == "__main__":
    main()
