"""Command line for `suitecheck`.

Two subcommands, and the split is the point:

* ``check`` is static. It reads manifests and payload files and reports
  findings. It never runs anything from a manifest, so it is safe to run in CI
  over a suite someone else wrote.
* ``run`` only lists the commands a manifest declares. It never executes them;
  installation and service lifecycle are the consuming Harness's responsibility.

Exit codes: 0 clean or inspected, 1 findings at error severity, 2 usage or manifest error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .manifest import MANIFEST_NAME, ManifestError, SuiteManifest, load_manifest
from .validate import duplicate_skills, errors, find_suites, validate_suite


def _discover(target: str) -> list[Path]:
    path = Path(target)
    if path.is_dir() and (path / MANIFEST_NAME).is_file():
        return [path]
    if path.is_dir():
        found = find_suites(path)
        if not found:
            raise SystemExit(f"no {MANIFEST_NAME} found under {target}")
        return found
    return [path]


def _check(targets: list[str]) -> int:
    total = 0
    failures = 0
    loaded: list[SuiteManifest] = []
    for target in targets:
        for suite_root in _discover(target):
            try:
                suite = load_manifest(suite_root)
            except ManifestError as error:
                print(error, file=sys.stderr)
                failures += 1
                continue
            loaded.append(suite)
            findings = validate_suite(suite)
            print(f"{suite.suite} ({suite.role}/{suite.effective_actor}) — {suite.title}")
            if not findings:
                print("  ok")
            for finding in findings:
                print(f"  {finding.render()}")
            total += len(findings)
            failures += len(errors(findings))
    if len(loaded) > 1:
        shared = duplicate_skills(loaded)
        print(f"{len(loaded)} suites together")
        if not shared:
            print("  ok")
        for finding in shared:
            print(f"  {finding.render()}")
        total += len(shared)
        failures += len(errors(shared))
    if failures:
        print(f"\n{failures} error(s), {total} finding(s) total", file=sys.stderr)
        return 1
    print(f"\nno errors, {total} finding(s) total")
    return 0


def _run(target: str, section: str) -> int:
    """List the commands a manifest declares. Never executes them."""
    suite = load_manifest(target)
    commands = suite.install if section == "install" else suite.check
    if not commands:
        print(f"{suite.suite} declares no {section} command", file=sys.stderr)
        return 2
    print(f"{suite.suite} declares {len(commands)} {section} command(s); suitecheck never executes them")
    for command in commands:
        print(f"  {command}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="suitecheck", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="statically validate one suite directory, manifest, or a directory of suites")
    check.add_argument("target", nargs="?", default=".")

    runner = sub.add_parser("run", help="list a manifest's declared commands without running them")
    runner.add_argument("section", choices=("install", "check"))
    runner.add_argument("target")

    args = parser.parse_args(argv)
    if args.command == "check":
        return _check([args.target])
    try:
        return _run(args.target, args.section)
    except ManifestError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
