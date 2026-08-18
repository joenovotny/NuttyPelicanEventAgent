import os

from dotenv import load_dotenv
from flask import Flask

from .models import db


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "local-development-only"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///events.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        OUTREACH_FROM_ADDRESS=os.getenv(
            "OUTREACH_FROM_ADDRESS", "EventPlanning@thenuttypelican.com"
        ),
        AUTOMATION_SEND_ENABLED=os.getenv("AUTOMATION_SEND_ENABLED", "false").lower() == "true",
        AUTOMATION_POLL_MINUTES=int(os.getenv("AUTOMATION_POLL_MINUTES", "10")),
        AUTOMATION_LOOKBACK_HOURS=int(os.getenv("AUTOMATION_LOOKBACK_HOURS", "72")),
        AUTOMATION_FOLLOW_UP_DAYS=int(os.getenv("AUTOMATION_FOLLOW_UP_DAYS", "3")),
        AUTOMATION_MAX_FOLLOW_UPS=int(os.getenv("AUTOMATION_MAX_FOLLOW_UPS", "2")),
        DISCOVERY_ENABLED=os.getenv("DISCOVERY_ENABLED", "false").lower() == "true",
        DISCOVERY_INTERVAL_HOURS=int(os.getenv("DISCOVERY_INTERVAL_HOURS", "24")),
        DISCOVERY_AUTO_QUALIFY=os.getenv("DISCOVERY_AUTO_QUALIFY", "false").lower() == "true",
        BRAVE_SEARCH_API_KEY=os.getenv("BRAVE_SEARCH_API_KEY", ""),
        BRAVE_MONTHLY_QUERY_LIMIT=int(os.getenv("BRAVE_MONTHLY_QUERY_LIMIT", "250")),
        OUTREACH_MENU_PATH=os.getenv("OUTREACH_MENU_PATH", ""),
        OUTREACH_PHOTO_PATHS=[value.strip() for value in os.getenv("OUTREACH_PHOTO_PATHS", "").split(",") if value.strip()],
        ALERT_EMAIL_ADDRESS=os.getenv("ALERT_EMAIL_ADDRESS", ""),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    from .routes import bp

    app.register_blueprint(bp)
    with app.app_context():
        db.create_all()

    @app.cli.command("seed")
    def seed_command():
        """Load starter Wilmington-area candidate events."""
        from .seed import seed_events

        print(f"Added {seed_events()} candidate events.")

    @app.cli.command("sync-inbox")
    def sync_inbox_command():
        """Import and parse recent organizer replies from Microsoft 365."""
        from .inbox import sync_inbox, sync_sent_items

        print(f"Processed {sync_inbox()} organizer replies and {sync_sent_items()} sent messages.")

    @app.cli.command("automation-once")
    def automation_once_command():
        """Run one inbox and bounded-outreach automation cycle."""
        from .automation import run_automation_once

        print(run_automation_once())

    @app.cli.command("automation-worker")
    def automation_worker_command():
        """Run the continuous local automation worker."""
        from .automation import run_worker

        run_worker()

    @app.cli.command("discover-now")
    def discover_now_command():
        """Discover candidate events from configured official sources."""
        from .discovery import discover_events

        print(discover_events())
    return app
