#!/usr/bin/env python3
"""Manual smoke test for the SciencePal API.

Usage (from the bridge project directory):

    uv run python scripts/smoke.py --list-agents
    uv run python scripts/smoke.py --prompt "Hello" --timeout 120
    uv run python scripts/smoke.py --prompt "Run the task" --file inputs/iris.csv --download

The token is read from SCIENCEPAL_ACCESS_TOKEN (or the project .env). This
script prints ids and status only; it never prints the token.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from sciencepal_bridge.client import HttpSciencePalClient, SciencePalError
from sciencepal_bridge.config import BridgeConfig, ConfigError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-agents", action="store_true")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    try:
        config = BridgeConfig.from_env()
        config.require_token()
    except (ConfigError, SciencePalError) as error:
        code = getattr(error, "code", "sciencepal_config_error")
        print(json.dumps({"error": {"code": code, "message": str(error)}}, ensure_ascii=False))
        return 1

    client = HttpSciencePalClient(
        base_url=config.base_url,
        access_token=config.access_token,
        timeout=config.request_timeout_s,
    )

    try:
        if args.list_agents or not args.prompt:
            agents = client.list_agents()
            print(json.dumps({"agents": agents}, ensure_ascii=False, indent=2))
            if not args.prompt:
                return 0

        files = []
        for raw in args.file:
            path = config.resolve_input(raw)
            files.append({"name": path.name, "path": str(path)})
        from sciencepal_bridge.service import SciencePalService

        service = SciencePalService(config, client=client)
        started = service.start(
            instruction=args.prompt,
            idempotency_key=f"smoke:{int(time.time())}",
            files=files,
            agent_id=args.agent_id,
        )
        print(json.dumps({"started": started}, ensure_ascii=False, indent=2))

        deadline = time.monotonic() + args.timeout
        status = {}
        while time.monotonic() < deadline:
            status = service.status(started["run_id"])
            print(json.dumps({"status": status}, ensure_ascii=False))
            if status.get("terminal"):
                break
            time.sleep(args.interval)
        else:
            print(json.dumps({"error": "timeout"}, ensure_ascii=False))
            return 2

        if args.download and status.get("status") == "completed":
            collected = service.collect(started["run_id"])
            print(json.dumps({"collected": collected}, ensure_ascii=False, indent=2))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
