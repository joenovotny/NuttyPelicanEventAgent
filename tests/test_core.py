import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import create_app
from app.guardrails import GuardrailViolation, validate_outbound
from app.inbox import match_event
from app.models import Event, db
from app.parser import parse_organizer_response
from app.routes import _event_subject
from app.automation import run_automation_once
from app.discovery import parse_event_page


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

    def test_closed_vendor_response_is_declined(self):
        result = parse_organizer_response("We are not accepting food vendors this year.")
        self.assertEqual(result["updates"]["status"], "Declined/Skip")

    def test_not_open_yet_is_scheduled_for_research(self):
        result = parse_organizer_response("Vendor applications are not open yet. Please check back.")
        self.assertEqual(result["updates"]["status"], "Researching")

    def test_detects_menu_and_photo_request(self):
        result = parse_organizer_response("Could you send your menu and pricing plus product photos?")
        self.assertEqual(result["material_requests"], ["menu", "photos"])


class DiscoveryParserTests(unittest.TestCase):
    def test_official_vendor_page_can_qualify_event(self):
        html = """
        <html><h1>Riverfront Food Festival</h1>
        <p>Food vendor applications are open. Contact vendors@festival.example.</p>
        <a href="/vendor-application">Vendor application</a>
        <script type="application/ld+json">{
          "@type":"Event", "name":"Riverfront Food Festival",
          "startDate":"2026-10-03", "location":{"address":{"addressLocality":"Wilmington","addressRegion":"NC"}}
        }</script></html>
        """
        result = parse_event_page("https://festival.example/event", html, "Official calendar")
        self.assertEqual(result["status"], "Qualified")
        self.assertEqual(result["contact_email"], "vendors@festival.example")
        self.assertEqual(result["start_date"], "2026-10-03")

    def test_email_without_vendor_signal_is_not_auto_qualified(self):
        html = "<h1>Community Festival</h1><p>Wilmington, NC. Contact info@example.org for details.</p>"
        result = parse_event_page("https://example.org/event", html, "Official calendar")
        self.assertEqual(result["status"], "Researching")
        self.assertEqual(result["contact_email"], "")


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


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "AUTOMATION_SEND_ENABLED": True,
            "AUTOMATION_FOLLOW_UP_DAYS": 3,
            "AUTOMATION_MAX_FOLLOW_UPS": 2,
            "AUTOMATION_LOOKBACK_HOURS": 72,
            "DISCOVERY_ENABLED": False,
            "DISCOVERY_AUTO_QUALIFY": False,
            "OUTREACH_MENU_PATH": "",
            "OUTREACH_PHOTO_PATHS": [],
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @patch("app.automation.sync_inbox", return_value=0)
    @patch("app.automation.sync_sent_items", return_value=0)
    @patch("app.automation.GraphEmailClient.send")
    def test_qualified_event_gets_one_tagged_outreach(self, send, sent_sync, inbox_sync):
        event = Event(name="Automation Test", contact_email="organizer@example.com", status="Qualified")
        db.session.add(event)
        db.session.commit()
        result = run_automation_once(datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(result["sent"], 1)
        self.assertEqual(event.status, "Waiting")
        self.assertIn(f"[NP-EVENT-{event.id:04d}]", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
