"""The notification rules the email-service actually enforces (ai4-x0ay).

Every check here mirrors a line of `_content_problem` in
`centre-control/email-service/src/email_service/service.py`. They are duplicated
on purpose: the service returns one opaque ``invalid`` for all of them, so a
researcher with a 240-character subject would otherwise have no idea what went
wrong. The service stays authoritative — nothing here is used to skip calling it.
"""

from __future__ import annotations

import unittest

from work_agent_runtime.notifications import (
    BODY_MAX_CHARS,
    NOTIFICATION_KIND,
    SUBJECT_MAX_CHARS,
    build_intent,
    dedupe_key,
    notification_brief,
    notification_problem,
)


def _intent(**overrides):
    values = {
        "execution_id": "exec-1",
        "task_node_id": "node-1",
        "recipient_principal_id": "person:owner",
        "subject": "Draft is ready for review",
        "body": "A draft for node-1 is waiting for your review.",
    }
    values.update(overrides)
    return build_intent(**values)


class BuildIntentTests(unittest.TestCase):
    def test_the_runtime_fills_the_three_fields_a_model_cannot_guess(self) -> None:
        intent = _intent().to_dict()
        self.assertEqual(intent["dedupe_key"], "draft-ready:exec-1")
        self.assertEqual(intent["related"], {"execution_id": "exec-1", "task_node_id": "node-1"})
        self.assertEqual(intent["schema_version"], "1")

    def test_schema_version_is_a_string_not_an_integer(self) -> None:
        """The service compares against `"1"`; the integer 1 is rejected."""
        self.assertIsInstance(_intent().to_dict()["schema_version"], str)

    def test_the_kind_is_one_of_the_configured_thirteen(self) -> None:
        self.assertEqual(NOTIFICATION_KIND, "draft_ready")
        self.assertNotEqual(NOTIFICATION_KIND, "task_agent_run_finished")

    def test_recipients_are_principal_id_objects(self) -> None:
        self.assertEqual(_intent().to_dict()["recipients"], [{"principal_id": "person:owner"}])

    def test_the_dedupe_key_is_derived_from_the_execution(self) -> None:
        """Two handoffs of the same execution must collide, not both send."""
        self.assertEqual(dedupe_key("exec-1"), dedupe_key("exec-1"))
        self.assertNotEqual(dedupe_key("exec-1"), dedupe_key("exec-2"))

    def test_notification_ids_differ_between_intents(self) -> None:
        self.assertNotEqual(_intent().notification_id, _intent().notification_id)


class ContentRuleTests(unittest.TestCase):
    def test_a_well_formed_intent_has_no_problem(self) -> None:
        self.assertIsNone(notification_problem(_intent()))

    def test_the_mapping_form_is_accepted_too(self) -> None:
        self.assertIsNone(notification_problem(_intent().to_dict()))

    def test_a_subject_over_two_hundred_characters_is_named(self) -> None:
        problem = notification_problem(_intent(subject="s" * (SUBJECT_MAX_CHARS + 1)))
        self.assertEqual(problem, "subject_too_long")

    def test_a_subject_exactly_at_the_limit_passes(self) -> None:
        self.assertIsNone(notification_problem(_intent(subject="s" * SUBJECT_MAX_CHARS)))

    def test_a_body_over_four_thousand_characters_is_named(self) -> None:
        problem = notification_problem(_intent(body="b" * (BODY_MAX_CHARS + 1)))
        self.assertEqual(problem, "body_too_long")

    def test_html_markup_is_refused_in_either_field(self) -> None:
        self.assertEqual(
            notification_problem(_intent(subject="<b>ready</b>")), "html_not_allowed"
        )
        self.assertEqual(
            notification_problem(_intent(body="see <a href='#'>this</a>")),
            "html_not_allowed",
        )

    def test_a_control_character_is_refused(self) -> None:
        self.assertEqual(
            notification_problem(_intent(body="draft ready\x07")), "control_character_not_allowed"
        )

    def test_a_newline_and_a_tab_are_allowed(self) -> None:
        """A multi-paragraph body is normal; only C0 controls are refused."""
        self.assertIsNone(notification_problem(_intent(body="line one\n\tline two")))

    def test_an_empty_recipient_list_is_refused(self) -> None:
        intent = _intent().to_dict()
        intent["recipients"] = []
        self.assertEqual(notification_problem(intent), "recipients_empty")

    def test_a_recipient_without_a_principal_id_is_refused(self) -> None:
        intent = _intent().to_dict()
        intent["recipients"] = [{"principal_id": "  "}]
        self.assertEqual(notification_problem(intent), "recipient_without_principal_id")

    def test_related_as_null_is_refused(self) -> None:
        """The ticket singles this out: `null` is the natural mistake."""
        intent = _intent().to_dict()
        intent["related"] = None
        self.assertEqual(notification_problem(intent), "related_not_an_object")

    def test_the_integer_schema_version_is_refused(self) -> None:
        intent = _intent().to_dict()
        intent["schema_version"] = 1
        self.assertEqual(notification_problem(intent), "schema_version_not_string_1")

    def test_an_empty_dedupe_key_is_refused(self) -> None:
        intent = _intent().to_dict()
        intent["dedupe_key"] = ""
        self.assertEqual(notification_problem(intent), "dedupe_key_empty")

    def test_an_empty_subject_is_refused(self) -> None:
        self.assertEqual(notification_problem(_intent(subject="   ")), "empty_subject_or_body")


class BriefTests(unittest.TestCase):
    def test_the_brief_carries_the_exact_values_the_runtime_owns(self) -> None:
        brief = notification_brief(execution_id="exec-9", task_node_id="node-9")
        self.assertIn("draft-ready:exec-9", brief)
        self.assertIn('"execution_id": "exec-9"', brief)
        self.assertIn('"task_node_id": "node-9"', brief)
        self.assertIn('"schema_version": "1"', brief)
        self.assertIn("draft_ready", brief)

    def test_the_brief_does_not_invent_the_owner(self) -> None:
        """The owner comes from the mapping; a wrong address mails a stranger."""
        brief = notification_brief(execution_id="e", task_node_id="n")
        self.assertIn("task_owner_id", brief)
        self.assertNotIn("person:", brief)

    def test_the_brief_tells_the_agent_not_to_retry(self) -> None:
        """A retry storm against a broken Registry is worse than one failure."""
        self.assertIn("不要重试", notification_brief(execution_id="e", task_node_id="n"))

    def test_the_brief_keeps_the_draft_when_the_mail_fails(self) -> None:
        """Losing a finished draft over an unreachable mailbox would be worse."""
        brief = notification_brief(execution_id="e", task_node_id="n")
        self.assertIn("notification_error", brief)
        self.assertIn("也不要让整轮执行失败", brief)


class WriterPromptTests(unittest.TestCase):
    """The brief is appended only for a writer that actually holds the card."""

    def _run(self, writer_servers, capture):
        from work_agent_runtime import FakeDraftBox, WorkflowExecutor, load_config

        config = load_config(
            {
                "agents": {
                    "entry": {
                        "identity": "e",
                        "instruction": "e",
                        "model": "fake",
                        "allowed_mcp_resources": [],
                        "resources": [],
                    },
                    "writer": {
                        "identity": "w",
                        "instruction": "w",
                        "model": "fake",
                        "allowed_mcp_resources": writer_servers,
                        "resources": [],
                    },
                },
                "workflows": {
                    "main": {
                        "type": "Orchestrator",
                        "entry_agent": "entry",
                        "sub_agents": ["entry"],
                        "summarizer": "entry",
                        "final_writer": "writer",
                    }
                },
            },
            known_mcp_resources={"email-service", "draft-buffer"},
        )

        def agent(name, prompt, tools=None):
            if name == "writer":
                capture.append(prompt)
                return '{"draft_id": "3f12df3e-1111-4222-8333-444455556666", "summary": "ok"}'
            return "intermediate"

        WorkflowExecutor(config, agent, FakeDraftBox()).run("main", "go", target_id="exec-1")

    def test_a_writer_with_the_email_card_is_told_the_three_fixed_fields(self) -> None:
        captured: list[str] = []
        self._run(["email-service", "draft-buffer"], captured)
        self.assertIn("draft-ready:exec-1", captured[0])

    def test_a_writer_without_the_email_card_is_not_told_about_notifications(self) -> None:
        """Otherwise the model would try to send a notification it has no tool for."""
        captured: list[str] = []
        self._run(["draft-buffer"], captured)
        self.assertNotIn("send_notification", captured[0])


if __name__ == "__main__":
    unittest.main()
