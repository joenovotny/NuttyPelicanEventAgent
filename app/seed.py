from .models import Event, db

SEED_EVENTS = [
    dict(name="NC Spot Festival", location="Hampstead, NC", status="Qualified", score=96, notes="High-priority two-day community festival. Verify every contact and payment request through an independently published official channel."),
    dict(name="Autumn with Topsail", location="Topsail Beach, NC", status="Qualified", score=92, drive_minutes=50, website="https://autumnwithtopsail.com/", notes="Established multi-day festival with a dedicated food-vendor contact."),
    dict(name="North Carolina Blueberry Festival", location="Burgaw, NC", status="Researching", score=89, drive_minutes=35, notes="Must-apply-early candidate; monitor next application cycle."),
    dict(name="Festival Latino", location="Wilmington, NC", status="Discovered", score=87, drive_minutes=20, notes="Two-day family event with a food courtyard; confirm vendor availability."),
    dict(name="Oktoberfest on the Beach", location="Carolina Beach, NC", status="Discovered", score=90, drive_minutes=35, notes="Exceptionally strong product fit for Bavarian-style cinnamon-glazed nuts."),
    dict(name="North Carolina Holiday Flotilla", location="Wrightsville Beach, NC", status="Researching", score=85, drive_minutes=25, notes="Major local holiday tradition; investigate official vending opportunities."),
    dict(name="Really Cool Stuff Holiday Market", location="Wilmington, NC", status="Application Open", score=82, drive_minutes=15, notes="Holiday impulse-buy fit. Joe must complete any application."),
    dict(name="BAD Day Music & Arts Festival", location="Wilmington, NC", status="Discovered", score=78, drive_minutes=15, notes="Compare scheduling and economics against Festival Latino."),
    dict(name="Wilmington Riverfest", location="Wilmington, NC", status="Researching", score=84, drive_minutes=15, notes="Strong attendance fit; monitor future food-vendor application opening and fee."),
    dict(name="Southport Spring Festival", location="Southport, NC", status="Researching", score=76, drive_minutes=50, notes="Established downtown community festival; monitor next application cycle."),
]


def seed_events():
    if Event.query.count():
        return 0
    db.session.add_all(Event(**data) for data in SEED_EVENTS)
    db.session.commit()
    return len(SEED_EVENTS)

