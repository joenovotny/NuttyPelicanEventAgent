import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from flask import current_app

from .models import Alert, AutomationState, Event, db


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "discovery_sources.json"
USER_AGENT = "NuttyPelicanEventAgent/1.0 (official event research)"


def _config():
    return json.loads(CONFIG_PATH.read_text())


def _text(soup):
    return " ".join(soup.stripped_strings)


def _json_ld_events(soup):
    events = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "Event":
                events.append(candidate)
            if isinstance(candidate, dict) and isinstance(candidate.get("@graph"), list):
                events.extend(item for item in candidate["@graph"] if isinstance(item, dict) and item.get("@type") == "Event")
    return events


def _date(value):
    if not value:
        return ""
    try:
        return parse_date(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def parse_event_page(url, html, source_name, config=None):
    config = config or _config()
    soup = BeautifulSoup(html, "html.parser")
    text = _text(soup)
    lowered = text.lower()
    structured = (_json_ld_events(soup) or [{}])[0]
    heading = soup.select_one('[id$="eventTitle"]') or soup.find("h1")
    name = structured.get("name") or (heading.get_text(" ", strip=True) if heading else "")
    generic_headings = {"calendar", "events", "street fair", "what we need from you", "thank you to our sponsors!"}
    if name.strip().lower() in generic_headings and soup.title:
        title = soup.title.get_text(" ", strip=True)
        if title:
            name = re.split(r"\s+[|–—]\s+", title)[0].strip()
    if not name or not any(signal in f"{name} {lowered}" for signal in config["event_signals"]):
        return None
    area_text = f"{lowered} {json.dumps(structured).lower()}"
    if not any(signal in area_text for signal in config["area_signals"]):
        return None
    if any(signal in f"{name.lower()} {json.dumps(structured).lower()}" for signal in config["excluded_area_signals"]):
        return None

    vendor_signal = next((signal for signal in config["vendor_signals"] if signal in lowered), "")
    emails = []
    for link in soup.select('a[href^="mailto:"]'):
        found = EMAIL_PATTERN.findall(link.get("href", ""))
        context = link.parent.get_text(" ", strip=True).lower() if link.parent else ""
        for email in found:
            if "vendor" in email.lower() or any(signal in context for signal in config["vendor_signals"]):
                emails.append(email)
    for match in EMAIL_PATTERN.finditer(text):
        context = text[max(0, match.start() - 300):match.end() + 300].lower()
        if "vendor" in match.group(0).lower() or any(signal in context for signal in config["vendor_signals"]):
            emails.append(match.group(0))
    emails = list(dict.fromkeys(email.lower() for email in emails))

    application_url = ""
    for link in soup.select("a[href]"):
        label = f"{link.get_text(' ', strip=True)} {link.get('href', '')}".lower()
        if "vendor" in label and any(word in label for word in ("apply", "application", "register")):
            application_url = urljoin(url, link["href"])
            break

    location = structured.get("location", {})
    if isinstance(location, dict):
        address = location.get("address", "")
        if isinstance(address, dict):
            location = ", ".join(str(address.get(key, "")) for key in ("streetAddress", "addressLocality", "addressRegion") if address.get(key))
        else:
            location = address or location.get("name", "")
    else:
        location = str(location or "")

    host = (urlparse(url).hostname or "").lower()
    is_aggregator = any(host == value or host.endswith(f".{value}") for value in config["aggregator_hosts"])
    food_specific = "food" in name.lower() or "food truck" in name.lower()
    can_auto_qualify = bool(emails and vendor_signal and food_specific and not is_aggregator)
    start_date = _date(structured.get("startDate"))
    if not start_date:
        date_node = soup.select_one('[itemprop="startDate"]')
        start_date = _date(date_node.get("content") or date_node.get_text(" ", strip=True)) if date_node else ""
    generic_listing = any(phrase in name.lower() for phrase in ("events - 2026 schedule", "festivals events", "festivals near", "fairs, festivals & events", "food truck festivals in"))
    if generic_listing and not vendor_signal and not start_date:
        return None
    return {
        "name": name[:160],
        "website": url,
        "location": location[:160],
        "start_date": start_date,
        "end_date": _date(structured.get("endDate")),
        "contact_email": emails[0] if can_auto_qualify else "",
        "application_url": application_url,
        "status": "Qualified" if can_auto_qualify else "Researching",
        "score": 80 if can_auto_qualify else 55,
        "notes": f"Discovered from {source_name}. Official source verified {datetime.now(timezone.utc).date().isoformat()}." + (f" Vendor signal: {vendor_signal}." if vendor_signal else " Contact/vendor eligibility requires research."),
    }


def _candidate_links(source, html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for node in soup.select("a[href]"):
        url = urljoin(source["url"], node["href"]).split("#", 1)[0]
        parsed = urlparse(url)
        if parsed.hostname != source["allowed_host"]:
            continue
        if not any(pattern.lower() in url.lower() for pattern in source["link_patterns"]):
            continue
        if url.rstrip("/") == source["url"].split("?", 1)[0].rstrip("/"):
            continue
        links.append(url)
    return list(dict.fromkeys(links))[:40]


def _brave_query(session, query, count=10):
    key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not key:
        return [], "Broad web search is not configured: BRAVE_SEARCH_API_KEY is empty."
    month_key = f"brave_queries_{datetime.now(timezone.utc):%Y-%m}"
    state = db.session.get(AutomationState, month_key) or AutomationState(key=month_key, value="0")
    used = int(state.value or 0)
    limit = int(os.getenv("BRAVE_MONTHLY_QUERY_LIMIT", "250"))
    if used >= limit:
        return [], f"Brave monthly query limit reached ({limit})."
    state.value = str(used + 1)
    db.session.add(state)
    try:
        response = session.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            params={"q": query, "count": count, "country": "us", "search_lang": "en"},
            timeout=20,
        )
        response.raise_for_status()
        links = [item.get("url", "") for item in response.json().get("web", {}).get("results", [])]
        return [url for url in dict.fromkeys(links) if url.startswith("http")], None
    except (requests.RequestException, ValueError) as exc:
        return [], f"Brave search '{query}': {exc}"


def _brave_links(session, config):
    links = []
    errors = []
    for query in config["search_queries"]:
        result, error = _brave_query(session, query, 10)
        links.extend(result)
        if error:
            errors.append(error)
            if "monthly query limit" in error or "not configured" in error:
                break
    return list(dict.fromkeys(links)), errors


def _attempts(event_id):
    state = db.session.get(AutomationState, f"research_attempts_{event_id}")
    return int(state.value or 0) if state else 0


def _set_attempts(event_id, value):
    key = f"research_attempts_{event_id}"
    state = db.session.get(AutomationState, key) or AutomationState(key=key)
    state.value = str(value)
    db.session.add(state)


def _same_event(original_name, candidate_name):
    ignored = {"festival", "fest", "event", "events", "vendor", "vendors", "application", "food", "2026", "the", "and"}
    original = {word for word in re.findall(r"[a-z0-9]+", original_name.lower()) if len(word) > 3 and word not in ignored}
    candidate = {word for word in re.findall(r"[a-z0-9]+", candidate_name.lower()) if len(word) > 3 and word not in ignored}
    return bool(original & candidate)


def research_queue(session, config, auto_qualify):
    events = Event.query.filter_by(status="Researching").all()
    events.sort(key=lambda event: (_attempts(event.id), event.created_at.isoformat() if event.created_at else ""))
    researched = promoted = action_required = 0
    errors = []
    for event in events[:current_app.config["RESEARCH_BATCH_SIZE"]]:
        attempts = _attempts(event.id) + 1
        query = f'"{event.name}" food vendor application contact Wilmington NC'
        links, error = _brave_query(session, query, 5)
        if error:
            errors.append(error)
            if "monthly query limit" in error or "not configured" in error:
                break
        _set_attempts(event.id, attempts)
        researched += 1
        found = False
        for url in links:
            try:
                response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
                response.raise_for_status()
                data = parse_event_page(url, response.text, "event-specific research", config)
            except requests.RequestException:
                continue
            if not data or not _same_event(event.name, data["name"]):
                continue
            found = True
            for field in ("name", "location", "start_date", "end_date", "contact_email", "application_url", "score"):
                if data.get(field):
                    setattr(event, field, data[field])
            event.website = url
            event.notes = data["notes"] + f" Event-specific research attempt {attempts}."
            if auto_qualify and data["status"] == "Qualified":
                event.status = "Qualified"
                promoted += 1
            break
        if not found and attempts >= current_app.config["RESEARCH_MAX_ATTEMPTS"]:
            event.status = "Joe Action Required"
            db.session.add(Alert(event=event, kind="research-exhausted", title="Automated research needs help", detail=f"No verified food-vendor contact found after {attempts} searches."))
            action_required += 1
    return {"researched": researched, "promoted": promoted, "action_required": action_required, "errors": errors}


def discover_events(session=None, auto_qualify=False):
    session = session or requests.Session()
    config = _config()
    created = qualified = promoted = checked = 0
    errors = []
    for event in Event.query.filter(Event.status == "Researching", Event.notes.like("Discovered from%"), Event.website != "").all():
        try:
            response = session.get(event.website, headers={"User-Agent": USER_AGENT}, timeout=10)
            response.raise_for_status()
            checked += 1
            data = parse_event_page(event.website, response.text, "scheduled recheck", config)
        except requests.RequestException as exc:
            errors.append(f"{event.website}: {exc}")
            continue
        if not data:
            continue
        for field in ("name", "location", "start_date", "end_date", "contact_email", "application_url", "score"):
            if data.get(field):
                setattr(event, field, data[field])
        if auto_qualify and data["status"] == "Qualified":
            event.status = "Qualified"
            event.notes = data["notes"] + " Promoted after scheduled official-page recheck."
            promoted += 1
    for source in config["sources"]:
        if not source.get("automated", True):
            continue
        try:
            response = session.get(source["url"], headers={"User-Agent": USER_AGENT}, timeout=25)
            response.raise_for_status()
            links = _candidate_links(source, response.text)
        except requests.RequestException as exc:
            errors.append(f"{source['name']}: {exc}")
            continue
        for url in links:
            if Event.query.filter_by(website=url).first():
                continue
            try:
                response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
                response.raise_for_status()
                checked += 1
                data = parse_event_page(url, response.text, source["name"], config)
            except requests.RequestException as exc:
                errors.append(f"{url}: {exc}")
                continue
            if not data:
                continue
            if data["status"] == "Qualified" and not auto_qualify:
                data["status"] = "Researching"
                data["notes"] += " Held for supervised discovery review."
            event = Event(**data)
            db.session.add(event)
            created += 1
            qualified += event.status == "Qualified"
    search_links, search_errors = _brave_links(session, config)
    errors.extend(search_errors)
    for url in search_links[:60]:
        if Event.query.filter_by(website=url).first():
            continue
        try:
            response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            response.raise_for_status()
            checked += 1
            data = parse_event_page(url, response.text, "Brave web search", config)
        except requests.RequestException as exc:
            errors.append(f"{url}: {exc}")
            continue
        if not data:
            continue
        if data["status"] == "Qualified" and not auto_qualify:
            data["status"] = "Researching"
            data["notes"] += " Held for supervised discovery review."
        event = Event(**data)
        db.session.add(event)
        created += 1
        qualified += event.status == "Qualified"
    research = research_queue(session, config, auto_qualify)
    errors.extend(research["errors"])
    state = db.session.get(AutomationState, "last_discovery_at") or AutomationState(key="last_discovery_at")
    state.value = datetime.now(timezone.utc).isoformat()
    db.session.add(state)
    db.session.commit()
    return {"checked": checked, "created": created, "qualified": qualified, "promoted": promoted, "research": research, "errors": errors}
