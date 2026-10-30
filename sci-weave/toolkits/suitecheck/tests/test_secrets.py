import unittest

from suitecheck.secrets import (
    ASSIGNMENT,
    contains_pasted_value,
    looks_like_secret_value,
)


class SharedSecretVocabularyTests(unittest.TestCase):
    """The exporter and the validator read credentials through this one module."""

    def test_assignment_matches_a_credential_name_and_keeps_the_value_whole(self):
        match = ASSIGNMENT.search('API_TOKEN="abc123"\n')
        self.assertIsNotNone(match)
        self.assertEqual(match.group("value"), '"abc123"')

    def test_a_prose_value_is_not_a_secret(self):
        self.assertFalse(looks_like_secret_value('"PURGE SCIWEAVE DATA"'))

    def test_a_placeholder_is_not_a_secret(self):
        self.assertFalse(looks_like_secret_value("<your-token>"))
        self.assertFalse(looks_like_secret_value("${OTHER_TOKEN}"))
        self.assertFalse(looks_like_secret_value("eyJhbGci..."))

    def test_a_realistic_value_is_a_secret(self):
        self.assertTrue(looks_like_secret_value("ghp_1234567890abcdef"))

    def test_documentation_pasting_a_value_is_flagged(self):
        self.assertTrue(contains_pasted_value("Set API_TOKEN=ghp_realtokenvalue123 here"))
        self.assertTrue(contains_pasted_value("Authorization: Bearer abcdef0123456789abcdef"))

    def test_documentation_naming_a_variable_with_a_placeholder_is_clean(self):
        self.assertFalse(contains_pasted_value("Set API_TOKEN=<your-token> before starting"))


if __name__ == "__main__":
    unittest.main()
