"""The deployment file has to agree with the source tree (ai4-349h).

This is a text assertion against `centre-stack/compose.yaml`, which is ugly and
deliberate. The failure it guards against actually happened in this repository and
is invisible to every other test: the rule-set file existed, was correct, and was
never in the image, so `append_prereview_log` answered `rule_set_missing` in
production while the whole suite passed.

Only the variables that decide *which files are read* are asserted here. Ports and
tokens belong to the deployment's own review.
"""

from __future__ import annotations

import re
import unittest

import yaml

from task_agent_worker.assembly import centre_root

#: Where the Dockerfile puts `centre-control/centre-agents/`. Spelled once: an
#: assertion that hardcodes it per-line turns a move into six edits and one miss.
APP_ROOT = "/app/centre-agents"

_DEFAULTED = re.compile(r"^\$\{([A-Z0-9_]+):-([^}]*)\}$")


def _default(value: str) -> str:
    """`${VAR:-default}` -> `default`; a literal passes through.

    Deliberately does *not* read this process's environment. Compose substitutes
    from the deployment's `.env`, so honouring the test runner's own exports would
    make the result depend on who runs the suite. The question here is only "is
    there a usable value when nobody overrides it".
    """
    match = _DEFAULTED.match(value)
    return match.group(2) if match else value


def _compose() -> dict:
    path = centre_root().parent.parent / "centre-stack" / "compose.yaml"
    if not path.is_file():  # pragma: no cover - the checkout always has it
        raise unittest.SkipTest(f"{path} is not present")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _environment() -> dict:
    return _compose()["services"]["centre"]["environment"]


class ContainerImageTests(unittest.TestCase):
    def test_the_image_copies_the_three_definition_directories(self) -> None:
        # The Dockerfile copies the whole `centre-agents/` tree, which is the only
        # reason definitions/, libs/mcp-libs/ and rules/ reach the container at
        # all. A narrower COPY list is a plausible future edit, so this pins the
        # consequence rather than the command.
        dockerfile = centre_root().parent.parent / "centre-stack" / "Dockerfile"
        if not dockerfile.is_file():  # pragma: no cover
            self.skipTest("centre-stack/Dockerfile is not present")
        text = dockerfile.read_text(encoding="utf-8")
        self.assertIn("COPY centre-control/centre-agents/ /app/centre-agents/", text)

    def test_the_worker_reads_the_shipped_directories_inside_the_image(self) -> None:
        environment = _environment()
        self.assertEqual(environment["CENTRE_DEFINITIONS_PATH"], f"{APP_ROOT}/definitions")
        self.assertEqual(environment["CENTRE_MCP_LIBS_PATH"], f"{APP_ROOT}/libs/mcp-libs")
        self.assertEqual(environment["CENTRE_RULES_DIR"], f"{APP_ROOT}/rules")

    def test_both_domains_resolve_the_same_rule_set_directory(self) -> None:
        # The writer records `rule_set_version`; each domain resolves that version
        # from its own rules directory. Two directories would let a report cite a
        # version the domain cannot resolve.
        environment = _environment()
        self.assertEqual(environment["SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR"], f"{APP_ROOT}/rules")
        self.assertEqual(environment["SCIWEAVE_WIKI_PREREVIEW_RULES_DIR"], f"{APP_ROOT}/rules")

    def test_the_cards_url_variables_resolve_without_an_override(self) -> None:
        # A card's `endpoint.url_env` that the deployment never sets fails at
        # startup, not at use — which is better than the reverse, but only if the
        # variable is actually there *and* has a value. The `:-` default is what
        # makes it true for a deployment that overrides nothing.
        environment = _environment()
        expected = {
            "RESEARCH_MAPPING_MCP_URL": "http://127.0.0.1:8710/mcp",
            "LLM_WIKI_MCP_URL": "http://127.0.0.1:8720/mcp",
            "EMAIL_MCP_URL": "http://127.0.0.1:8750/mcp",
        }
        for name, url in expected.items():
            with self.subTest(variable=name):
                self.assertIn(name, environment)
                self.assertEqual(_default(environment[name]), url)


if __name__ == "__main__":
    unittest.main()
