import unittest

from app.guardrails import GuardrailViolation, validate_outbound
from app.parser import parse_organizer_response


class ParserTests(unittest.TestCase):
    def test_extracts_event_facts_and_application_handoff(self):
        result = parse_organizer_response(
            "Applications are open. The food vendor fee is $350. "
            "Attendance was approximately 12,000. Application deadline: January 15. "
            "Apply at https://festival.example/vendor-application"
        )
        self.assertEqual(result["updates"]["vendor_fee"], "$350")
        self.assertEqual(result["updates"]["expected_attendance"], "12,000")
        self.assertEqual(result["updates"]["status"], "Joe Action Required")
        self.assertTrue(result["needs_human_review"])

    def test_flags_person_to_person_payment(self):
        result = parse_organizer_response("Please pay the booth fee by Zelle today.")
        self.assertIn("zelle", result["flags"])


class GuardrailTests(unittest.TestCase):
    def test_blocks_payment_authorization(self):
        with self.assertRaises(GuardrailViolation):
            validate_outbound("We will pay the vendor fee by Venmo today.")

    def test_allows_question_about_fee(self):
        validate_outbound("Could you provide the vendor fee and official application link?")

    def test_allows_standard_human_handoff_disclaimer(self):
        validate_outbound(
            "We are gathering information only. Joe will personally review and complete "
            "any application, agreement, or payment."
        )


if __name__ == "__main__":
    unittest.main()
