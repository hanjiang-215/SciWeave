"""Where an agent's skills come from, and what the worker does with them.

Two things are pinned here, and they are different failures:

* `load_skills` must refuse a declared-but-unusable directory, because a path
  typo that silently loads zero skills produces a worker that looks healthy and
  behaves as if the suite were never installed;
* an *unset* variable must stay unset. `fast_agent` defaults to scanning the
  home directory when nothing is passed, so "no skills" has to be handed over
  explicitly as ``skills=None`` rather than left to the framework.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from fast_agent_doubles import (
        FakeAgent as _FakeAgent,
        FakeSessionManager as _FakeSessionManager,
        Request as _Request,
        install as _install_fake,
        remove as _remove_fake_fast_agent,
    )
except ImportError:  # pragma: no cover
    from tests.fast_agent_doubles import (  # type: ignore[no-redef]
        FakeAgent as _FakeAgent,
        FakeSessionManager as _FakeSessionManager,
        Request as _Request,
        install as _install_fake,
        remove as _remove_fake_fast_agent,
    )

from work_agent_runtime.fast_agent_runtime import FastAgentDeepSeekRuntime, FastAgentSettings
from work_agent_runtime.skills import (
    LOCAL_VARIABLE,
    SHIPPED_VARIABLE,
    SkillsConfigError,
    load_skills,
)


def _skill(root: Path, name: str, *, body: str = "") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: does {name}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return directory


class LoadSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

    def test_nothing_declared_means_no_skills(self) -> None:
        config = load_skills({})
        self.assertEqual(config.directories, ())
        self.assertFalse(config)

    def test_a_declared_directory_is_kept_in_order(self) -> None:
        shipped = self.root / "shipped"
        local = self.root / "local"
        _skill(shipped, "alpha")
        _skill(local, "beta")
        config = load_skills({SHIPPED_VARIABLE: str(shipped), LOCAL_VARIABLE: str(local)})
        self.assertEqual(config.directories, (shipped, local))

    def test_the_shipped_variable_accepts_several_directories(self) -> None:
        first = self.root / "one"
        second = self.root / "two"
        _skill(first, "alpha")
        _skill(second, "beta")
        config = load_skills({SHIPPED_VARIABLE: os.pathsep.join([str(first), str(second)])})
        self.assertEqual(len(config), 2)

    def test_a_missing_directory_is_an_error(self) -> None:
        with self.assertRaises(SkillsConfigError) as caught:
            load_skills({SHIPPED_VARIABLE: str(self.root / "nope")})
        self.assertEqual(caught.exception.code, "skills_directory_missing")

    def test_pointing_at_a_skill_directory_is_named_explicitly(self) -> None:
        """The common mistake: the variable names the skill, not its parent."""
        skill = _skill(self.root / "skills", "alpha")
        with self.assertRaises(SkillsConfigError) as caught:
            load_skills({SHIPPED_VARIABLE: str(skill)})
        self.assertEqual(caught.exception.code, "skills_directory_is_a_skill")

    def test_a_directory_without_any_manifest_is_an_error(self) -> None:
        empty = self.root / "skills"
        (empty / "alpha").mkdir(parents=True)
        with self.assertRaises(SkillsConfigError) as caught:
            load_skills({SHIPPED_VARIABLE: str(empty)})
        self.assertEqual(caught.exception.code, "skills_directory_empty")

    def test_a_file_is_not_a_directory(self) -> None:
        path = self.root / "not-a-dir"
        path.write_text("x", encoding="utf-8")
        with self.assertRaises(SkillsConfigError) as caught:
            load_skills({SHIPPED_VARIABLE: str(path)})
        self.assertEqual(caught.exception.code, "skills_directory_not_a_directory")

    def test_a_directory_declared_twice_is_loaded_once(self) -> None:
        shipped = self.root / "shared"
        _skill(shipped, "alpha")
        config = load_skills(
            {SHIPPED_VARIABLE: str(shipped), LOCAL_VARIABLE: os.pathsep.join([str(shipped), str(shipped)])}
        )
        self.assertEqual(config.directories, (shipped,))


class RuntimeWiringTests(unittest.TestCase):
    """What the worker actually hands to `@fast.agent`."""

    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)
        self.addCleanup(_remove_fake_fast_agent)
        self.manager = _FakeSessionManager()
        self.agent = _FakeAgent(response="ok")
        self.recorded: list[dict] = []
        _install_fake(self.manager, self.agent, recorded=self.recorded)

    def _settings(self) -> FastAgentSettings:
        return FastAgentSettings(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            home=self.root / "home",
        )

    def test_declared_skill_directories_reach_the_decorator(self) -> None:
        skills = self.root / "skills"
        _skill(skills, "alpha")
        runtime = FastAgentDeepSeekRuntime(self._settings(), None, {SHIPPED_VARIABLE: str(skills)})
        runtime.run(_Request())
        self.assertEqual(self.recorded[0]["skills"], [skills])

    def test_without_a_declared_directory_skills_is_explicitly_none(self) -> None:
        """Not omitted: omitting means "scan the home directory" to fast-agent."""
        runtime = FastAgentDeepSeekRuntime(self._settings(), None, {})
        runtime.run(_Request())
        self.assertIn("skills", self.recorded[0])
        self.assertIsNone(self.recorded[0]["skills"])

    def test_a_wrong_directory_refuses_to_construct(self) -> None:
        with self.assertRaises(SkillsConfigError):
            FastAgentDeepSeekRuntime(self._settings(), None, {SHIPPED_VARIABLE: str(self.root / "missing")})

    def test_local_skills_come_last_so_they_win(self) -> None:
        shipped = self.root / "shipped"
        local = self.root / "local"
        _skill(shipped, "alpha")
        _skill(local, "alpha")
        runtime = FastAgentDeepSeekRuntime(
            self._settings(), None, {SHIPPED_VARIABLE: str(shipped), LOCAL_VARIABLE: str(local)}
        )
        runtime.run(_Request())
        self.assertEqual(self.recorded[0]["skills"], [shipped, local])


if __name__ == "__main__":
    unittest.main()
