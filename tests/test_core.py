import unittest

from app import create_app
from app.guardrails import GuardrailViolation, validate_outbound
from app.inbox import match_event
from app.models import Event, db
from app.parser import parse_organizer_response
from app.routes import _event_subject


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

    def test_extracts_permitted_products(self):
        result = parse_organizer_response(
            "Fresh cinnamon-glazed nuts and gourmet popcorn are permitted."
        )
        self.assertEqual(
            result["updates"]["product_rules"],
            "Fresh cinnamon-glazed nuts permitted; Gourmet popcorn permitted",
        )

    def test_currently_open_sets_application_status(self):
        result = parse_organizer_response("Applications are currently open.")
        self.assertEqual(result["updates"]["status"], "Application Open")


class EventTrackingTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_subject_contains_event_token(self):
        event = Event(id=12, name="Test")
        self.assertEqual(_event_subject(event, "Vendor inquiry"), "[NP-EVENT-0012] Vendor inquiry")

    def test_subject_token_wins_over_sender(self):
        target = Event(name="Target", contact_email="organizer@example.com")
        other = Event(name="Other", contact_email="organizer@example.com")
        db.session.add_all((target, other))
        db.session.commit()
        self.assertEqual(match_event(f"Re: [NP-EVENT-{target.id:04d}] Inquiry", "organizer@example.com"), target)

    def test_ambiguous_sender_without_token_is_not_matched(self):
        db.session.add_all((
            Event(name="One", contact_email="organizer@example.com"),
            Event(name="Two", contact_email="organizer@example.com"),
        ))
        db.session.commit()
        self.assertIsNone(match_event("Re: inquiry", "organizer@example.com"))


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
