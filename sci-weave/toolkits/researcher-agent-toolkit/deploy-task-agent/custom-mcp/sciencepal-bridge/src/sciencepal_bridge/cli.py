"""Command-line interface for harnesses that can run shell commands but do not
speak MCP. Every command prints one JSON object so the caller can parse it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import SciencePalError
from .config import BridgeConfig, ConfigError
from .service import SciencePalService

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_SCIENCEPAL = 2


def _service() -> SciencePalService:
    return SciencePalService(BridgeConfig.from_env())


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _error(error: Exception) -> int:
    code = getattr(error, "code", "sciencepal_internal")
    _print({"error": {"code": code, "message": str(error)}})
    return EXIT_SCIENCEPAL if isinstance(error, SciencePalError) else EXIT_CONFIG


def _read_instruction(args: argparse.Namespace) -> str:
    if args.instruction_file:
        return Path(args.instruction_file).read_text(encoding="utf-8")
    return args.instruction or ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sciencepal", description="SciencePal execution bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    agents = sub.add_parser("agents", help="list visible SciencePal agents")
    agents.set_defaults(handler=_agents)

    start = sub.add_parser("start", help="start one SciencePal run")
    start.add_argument("--instruction", default="")
    start.add_argument("--instruction-file", default="")
    start.add_argument("--idempotency-key", required=True)
    start.add_argument("--execution-id", default="")
    start.add_argument("--file", action="append", default=[])
    start.add_argument("--agent-id", default="")
    start.add_argument("--auto", action="store_true")
    start.add_argument("--no-web-search", action="store_true")
    start.add_argument("--model", default="")
    start.set_defaults(handler=_start)

    status = sub.add_parser("status", help="read one run status")
    status.add_argument("run_id")
    status.set_defaults(handler=_status)

    collect = sub.add_parser("collect", help="download artifacts for a completed run")
    collect.add_argument("run_id")
    collect.add_argument("--name", action="append", default=[])
    collect.add_argument("--root", action="append", default=[])
    collect.set_defaults(handler=_collect)

    cancel = sub.add_parser("cancel", help="stop a queued or running run")
    cancel.add_argument("run_id")
    cancel.set_defaults(handler=_cancel)

    return parser


def _agents(_: argparse.Namespace) -> int:
    return _run(lambda service: service.list_agents())


def _start(args: argparse.Namespace) -> int:
    return _run(
        lambda service: service.start(
            instruction=_read_instruction(args),
            idempotency_key=args.idempotency_key,
            execution_id=args.execution_id,
            files=[{"path": path} for path in args.file],
            agent_id=args.agent_id,
            agent_select_type="auto" if args.auto else "manual",
            web_search=not args.no_web_search,
            model_name=args.model,
        )
    )


def _status(args: argparse.Namespace) -> int:
    return _run(lambda service: service.status(args.run_id))


def _collect(args: argparse.Namespace) -> int:
    return _run(
        lambda service: service.collect(
            args.run_id,
            names=args.name or None,
            roots=args.root or None,
        )
    )


def _cancel(args: argparse.Namespace) -> int:
    return _run(lambda service: service.cancel(args.run_id))


def _run(action) -> int:
    try:
        _print(action(_service()))
        return EXIT_OK
    except (SciencePalError, ConfigError) as error:
        return _error(error)
    except Exception:
        _print({"error": {"code": "sciencepal_internal", "message": "unexpected bridge error"}})
        return EXIT_CONFIG


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
