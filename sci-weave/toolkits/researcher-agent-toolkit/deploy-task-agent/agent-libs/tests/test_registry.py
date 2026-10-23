import unittest

from agent_libs import (
    AgentResource,
    ResourceConflictError,
    ResourceKind,
    ResourceRegistry,
    ResourceVersionError,
)


class AgentLibRegistryTests(unittest.TestCase):
    def test_standard_samples_resolve_by_name_and_compatible_version(self):
        registry = ResourceRegistry()
        prompt = registry.resolve("research.prompt@1.0")
        self.assertEqual(prompt.kind, ResourceKind.PROMPT)
        self.assertEqual(prompt.version, "1.0.0")
        self.assertEqual(registry.resolve("research.format").kind, ResourceKind.FORMATTER)

    def test_local_resource_overrides_same_standard_version_without_mutating_standard(self):
        local_value = {"format": "json"}
        local = AgentResource("research.format", "1.0.0", "formatter", local_value, source="local")
        registry = ResourceRegistry(local=(local,))
        self.assertEqual(registry.resolve("research.format@1").value, local_value)
        local_value["format"] = "changed-after-registration"
        self.assertEqual(registry.resolve("research.format@1").value, {"format": "json"})
        self.assertEqual(registry.resolve("research.prompt").source, "standard")

    def test_conflict_and_incompatible_version_have_stable_codes(self):
        duplicate = AgentResource("research.prompt", "1.0.0", "prompt", "other", source="standard")
        with self.assertRaisesRegex(ResourceConflictError, r"\[resource_conflict\]"):
            ResourceRegistry(standard=(duplicate, duplicate))
        with self.assertRaisesRegex(ResourceVersionError, r"\[incompatible_resource_version\]"):
            ResourceRegistry().resolve("research.prompt@2")

    def test_local_new_resource_is_discoverable_as_config_reference(self):
        local = AgentResource("lab.prompt", "2.1.0", "prompt", "local", source="local")
        registry = ResourceRegistry(local=(local,))
        self.assertIn("lab.prompt@2.1.0", registry.references())
        # The registry is iterable so runtime config can use it as known resources.
        self.assertIn("lab.prompt@2.1.0", set(registry))


if __name__ == "__main__":
    unittest.main()
