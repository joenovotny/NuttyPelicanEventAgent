from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .email_service import GraphEmailClient, GraphNotConfigured
from .guardrails import GuardrailViolation
from .models import Event, Message, STATUSES, db
from .parser import parse_organizer_response
from .questions import missing_questions
from .seed import seed_events

bp = Blueprint("main", __name__)


@bp.get("/")
def dashboard():
    selected = request.args.get("status", "")
    query = Event.query.order_by(Event.score.desc().nullslast(), Event.name)
    events = query.filter_by(status=selected).all() if selected else query.all()
    counts = {status: Event.query.filter_by(status=status).count() for status in STATUSES}
    return render_template("dashboard.html", events=events, statuses=STATUSES, counts=counts, selected=selected)


@bp.route("/events/new", methods=["GET", "POST"])
def event_new():
    event = Event()
    if request.method == "POST":
        _update_event(event)
        db.session.add(event)
        db.session.commit()
        flash("Event added.", "success")
        return redirect(url_for("main.event_detail", event_id=event.id))
    return render_template("event_form.html", event=event, statuses=STATUSES, title="Add event")


@bp.route("/events/<int:event_id>", methods=["GET", "POST"])
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    if request.method == "POST":
        _update_event(event)
        db.session.commit()
        flash("Event updated.", "success")
        return redirect(url_for("main.event_detail", event_id=event.id))
    return render_template(
        "event_detail.html",
        event=event,
        statuses=STATUSES,
        questions=missing_questions(event),
        outreach=_outreach_draft(event),
    )


@bp.post("/events/<int:event_id>/parse")
def parse_response(event_id):
    event = db.get_or_404(Event, event_id)
    body = request.form.get("body", "").strip()
    if not body:
        flash("Paste the organizer response first.", "error")
        return redirect(url_for("main.event_detail", event_id=event.id))
    result = parse_organizer_response(body)
    for field, value in result["updates"].items():
        setattr(event, field, value)
    db.session.add(Message(event=event, direction="inbound", subject=request.form.get("subject", "Organizer response"), body=body))
    if not result["updates"] and event.status == "Waiting":
        event.status = "Follow-up Needed"
    db.session.commit()
    if result["flags"]:
        flash("Human review required. Safety flags: " + ", ".join(result["flags"]), "warning")
    flash(f"Saved response and extracted {len(result['updates'])} field(s). Review all changes.", "success")
    return redirect(url_for("main.event_detail", event_id=event.id))


@bp.post("/events/<int:event_id>/send")
def send_outreach(event_id):
    event = db.get_or_404(Event, event_id)
    body = request.form.get("body", "").strip()
    subject = request.form.get("subject", "").strip()
    try:
        GraphEmailClient().send(event.contact_email, subject, body)
    except (GraphNotConfigured, GuardrailViolation) as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.event_detail", event_id=event.id))
    event.status = "Waiting"
    event.last_contact_at = datetime.now(timezone.utc)
    db.session.add(Message(event=event, direction="outbound", subject=subject, body=body))
    db.session.commit()
    flash("Outreach sent and event moved to Waiting.", "success")
    return redirect(url_for("main.event_detail", event_id=event.id))


@bp.post("/seed")
def seed():
    count = seed_events()
    flash(f"Added {count} candidate events." if count else "Seed data already exists.", "success")
    return redirect(url_for("main.dashboard"))


def _update_event(event):
    text_fields = (
        "name", "location", "start_date", "end_date", "expected_attendance", "vendor_fee",
        "status", "website", "application_url", "contact_name", "contact_email",
        "application_deadline", "operating_hours", "food_vendor_count", "product_rules",
        "power_details", "permit_requirements", "insurance_requirements", "setup_details",
        "cancellation_policy", "notes",
    )
    for field in text_fields:
        if field in request.form:
            setattr(event, field, request.form.get(field, "").strip())
    for field in ("drive_minutes", "score"):
        value = request.form.get(field, "").strip()
        setattr(event, field, int(value) if value else None)


def _outreach_draft(event):
    greeting = f"Hi {event.contact_name}," if event.contact_name else "Hello," 
    questions = missing_questions(event)
    bullets = "\n".join(f"- {question}" for question in questions[:8])
    return f"""{greeting}

I'm reaching out on behalf of The Nutty Pelican about food-vendor opportunities for {event.name}. We serve fresh cinnamon-glazed almonds, cashews, and pecans, along with gourmet popcorn.

Could you help with the following details?

{bullets}

We are gathering information only. Joe will personally review and complete any application, agreement, or payment.

Thank you,
Nutty Pelican Events Team
Event coordination for Joe Novotny
{current_app.config['OUTREACH_FROM_ADDRESS']}"""

