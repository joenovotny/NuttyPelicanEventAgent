from datetime import datetime, timedelta, timezone
import re

from flask import current_app

from .email_service import GraphEmailClient
from .models import Alert, Event, Message, db
from .parser import parse_organizer_response
from .questions import missing_questions


EVENT_TOKEN = re.compile(r"\[NP-EVENT-(\d+)\]", re.IGNORECASE)


def match_event(subject, sender):
    """Prefer the durable subject token; use sender only when it is unambiguous."""
    token = EVENT_TOKEN.search(subject or "")
    if token:
        return db.session.get(Event, int(token.group(1)))
    matches = Event.query.filter(db.func.lower(Event.contact_email) == sender).limit(2).all()
    return matches[0] if len(matches) == 1 else None


def sync_inbox(since_hours=72):
    """Pull recent replies, match by sender email, extract facts, and save an audit trail."""
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat().replace("+00:00", "Z")
    messages = GraphEmailClient().recent_messages(since)
    processed = 0
    matched_events = {}
    events_with_updates = set()
    for item in messages:
        graph_id = item.get("id")
        if not graph_id or Message.query.filter_by(graph_message_id=graph_id).first():
            continue
        sender = (((item.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
        event = match_event(item.get("subject", ""), sender)
        if not event:
            continue
        matched_events[event.id] = event
        body = ((item.get("body") or {}).get("content") or "")
        result = parse_organizer_response(body)
        for field, value in result["updates"].items():
            setattr(event, field, value)
        if result["updates"]:
            events_with_updates.add(event.id)
        if result["flags"]:
            event.status = "Joe Action Required"
            db.session.add(Alert(
                event=event,
                kind="safety",
                title="Sensitive organizer request",
                detail="Detected terms requiring human review: " + ", ".join(result["flags"]),
            ))
        elif result["needs_human_review"]:
            db.session.add(Alert(
                event=event,
                kind="application-open",
                title="Application is open",
                detail="Review the organizer reply and complete the application personally.",
            ))
        elif result["updates"] and missing_questions(event):
            event.status = "Follow-up Needed"
            event.follow_up_at = datetime.now(timezone.utc) + timedelta(days=2)
        elif result["updates"]:
            event.status = "Qualified"
        db.session.add(Message(event=event, direction="inbound", subject=item.get("subject", ""), body=body, graph_message_id=graph_id))
        processed += 1
    for event_id, event in matched_events.items():
        if event_id not in events_with_updates and event.status == "Waiting":
            event.status = "Follow-up Needed"
    db.session.commit()
    return processed


def sync_sent_items(since_hours=72):
    """Record manually sent Outlook messages when their subject has an event token."""
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat().replace("+00:00", "Z")
    messages = GraphEmailClient().recent_sent_messages(since)
    processed = 0
    for item in messages:
        graph_id = item.get("id")
        if not graph_id or Message.query.filter_by(graph_message_id=graph_id).first():
            continue
        token = EVENT_TOKEN.search(item.get("subject", ""))
        if not token:
            continue
        event = db.session.get(Event, int(token.group(1)))
        if not event:
            continue
        body = ((item.get("body") or {}).get("content") or "")
        db.session.add(Message(
            event=event,
            direction="outbound",
            subject=item.get("subject", ""),
            body=body,
            graph_message_id=graph_id,
        ))
        event.status = "Waiting"
        event.last_contact_at = datetime.now(timezone.utc)
        event.follow_up_at = datetime.now(timezone.utc) + timedelta(days=current_app.config["AUTOMATION_FOLLOW_UP_DAYS"])
        processed += 1
    db.session.commit()
    return processed
