from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

STATUSES = [
    "Discovered",
    "Researching",
    "Qualified",
    "Contacted",
    "Waiting",
    "Follow-up Needed",
    "Application Open",
    "Joe Action Required",
    "Applied",
    "Accepted",
    "Declined/Skip",
]


def now_utc():
    return datetime.now(timezone.utc)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    location = db.Column(db.String(160), default="")
    start_date = db.Column(db.String(20), default="")
    end_date = db.Column(db.String(20), default="")
    drive_minutes = db.Column(db.Integer)
    expected_attendance = db.Column(db.String(80), default="")
    vendor_fee = db.Column(db.String(80), default="")
    status = db.Column(db.String(40), nullable=False, default="Discovered")
    score = db.Column(db.Integer)
    website = db.Column(db.String(500), default="")
    application_url = db.Column(db.String(500), default="")
    contact_name = db.Column(db.String(120), default="")
    contact_email = db.Column(db.String(200), default="")
    application_deadline = db.Column(db.String(80), default="")
    operating_hours = db.Column(db.String(160), default="")
    food_vendor_count = db.Column(db.String(80), default="")
    product_rules = db.Column(db.Text, default="")
    power_details = db.Column(db.Text, default="")
    permit_requirements = db.Column(db.Text, default="")
    insurance_requirements = db.Column(db.Text, default="")
    setup_details = db.Column(db.Text, default="")
    cancellation_policy = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    last_contact_at = db.Column(db.DateTime(timezone=True))
    follow_up_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)
    updated_at = db.Column(db.DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    messages = db.relationship(
        "Message", backref="event", lazy=True, cascade="all, delete-orphan"
    )


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    subject = db.Column(db.String(300), default="")
    body = db.Column(db.Text, nullable=False)
    graph_message_id = db.Column(db.String(300), unique=True)
    sent_at = db.Column(db.DateTime(timezone=True), default=now_utc)


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    kind = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    detail = db.Column(db.Text, default="")
    resolved = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)
    event = db.relationship("Event", backref="alerts")


class AutomationState(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, default="")


class MaterialRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    graph_message_id = db.Column(db.String(300), unique=True)
    requested = db.Column(db.String(120), nullable=False)
    fulfilled = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)
    event = db.relationship("Event", backref="material_requests")
