from datetime import datetime, timedelta, timezone

from .email_service import GraphEmailClient
from .models import Event, Message, db
from .parser import parse_organizer_response


def sync_inbox(since_hours=72):
    """Pull recent replies, match by sender email, extract facts, and save an audit trail."""
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat().replace("+00:00", "Z")
    messages = GraphEmailClient().recent_messages(since)
    processed = 0
    for item in messages:
        graph_id = item.get("id")
        if not graph_id or Message.query.filter_by(graph_message_id=graph_id).first():
            continue
        sender = (((item.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
        event = Event.query.filter(db.func.lower(Event.contact_email) == sender).first()
        if not event:
            continue
        body = ((item.get("body") or {}).get("content") or "")
        result = parse_organizer_response(body)
        for field, value in result["updates"].items():
            setattr(event, field, value)
        if not result["updates"] and event.status == "Waiting":
            event.status = "Follow-up Needed"
        db.session.add(Message(event=event, direction="inbound", subject=item.get("subject", ""), body=body, graph_message_id=graph_id))
        processed += 1
    db.session.commit()
    return processed

