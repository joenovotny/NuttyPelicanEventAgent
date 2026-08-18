import time
from datetime import datetime, timedelta, timezone

from flask import current_app

from .email_service import GraphEmailClient
from .inbox import sync_inbox, sync_sent_items
from .models import Alert, Event, Message, db
from .questions import missing_questions
from .routes import _event_subject, _outreach_draft


def create_alert(event, kind, title, detail=""):
    existing = Alert.query.filter_by(event_id=event.id, kind=kind, resolved=False).first()
    if existing:
        existing.title = title
        existing.detail = detail
        return existing
    alert = Alert(event=event, kind=kind, title=title, detail=detail)
    db.session.add(alert)
    return alert


def _follow_up_count(event):
    return Message.query.filter(
        Message.event_id == event.id,
        Message.direction == "outbound",
        Message.subject.ilike("%Follow-up%"),
    ).count()


def _follow_up_body(event):
    questions = missing_questions(event)[:5]
    bullets = "\n".join(f"- {question}" for question in questions)
    return f"""Hello,

I'm following up on our information request for {event.name}. Could you provide the remaining details below?

{bullets}

We are gathering information only. Joe will personally review and complete any application, agreement, or payment.

Thank you,
Nutty Pelican Events Team
{current_app.config['OUTREACH_FROM_ADDRESS']}"""


def _is_due(value, now):
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now


def run_automation_once(now=None):
    """Import replies and perform only enabled, bounded outreach actions."""
    now = now or datetime.now(timezone.utc)
    imported = sync_inbox(current_app.config["AUTOMATION_LOOKBACK_HOURS"])
    sent_imported = sync_sent_items(current_app.config["AUTOMATION_LOOKBACK_HOURS"])
    sent = 0
    stopped = 0

    if not current_app.config["AUTOMATION_SEND_ENABLED"]:
        return {"imported": imported, "sent_imported": sent_imported, "sent": sent, "stopped": stopped}

    due_events = Event.query.filter(
        Event.status.in_(("Qualified", "Waiting", "Follow-up Needed")),
        Event.contact_email != "",
    ).all()
    for event in due_events:
        try:
            if event.status == "Qualified":
                subject = _event_subject(event, f"Food vendor inquiry — {event.name}")
                body = _outreach_draft(event)
            else:
                if not _is_due(event.follow_up_at, now):
                    continue
                follow_up_count = _follow_up_count(event)
                if follow_up_count >= current_app.config["AUTOMATION_MAX_FOLLOW_UPS"]:
                    event.status = "Joe Action Required"
                    create_alert(event, "no-response", "Organizer did not respond", "Automatic follow-up limit reached.")
                    stopped += 1
                    continue
                subject = _event_subject(event, f"Follow-up {follow_up_count + 1} — {event.name}")
                body = _follow_up_body(event)

            GraphEmailClient().send(event.contact_email, subject, body)
            db.session.add(Message(event=event, direction="outbound", subject=subject, body=body))
            event.status = "Waiting"
            event.last_contact_at = now
            event.follow_up_at = now + timedelta(days=current_app.config["AUTOMATION_FOLLOW_UP_DAYS"])
            sent += 1
        except Exception as exc:
            event.status = "Joe Action Required"
            create_alert(event, "automation-error", "Automation stopped", str(exc))
            stopped += 1
    db.session.commit()
    return {"imported": imported, "sent_imported": sent_imported, "sent": sent, "stopped": stopped}


def run_worker():
    interval = current_app.config["AUTOMATION_POLL_MINUTES"] * 60
    while True:
        try:
            result = run_automation_once()
            print(f"Automation cycle: {result}", flush=True)
        except Exception as exc:
            db.session.rollback()
            print(f"Automation cycle failed and will retry: {exc}", flush=True)
        time.sleep(interval)
