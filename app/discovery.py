import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date

from .models import AutomationState, Event, db


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
    if not name or not any(signal in f"{name} {lowered}" for signal in config["event_signals"]):
        return None
    area_text = f"{lowered} {json.dumps(structured).lower()}"
    if not any(signal in area_text for signal in config["area_signals"]):
        return None

    vendor_signal = next((signal for signal in config["vendor_signals"] if signal in lowered), "")
    emails = []
    for link in soup.select('a[href^="mailto:"]'):
        emails.extend(EMAIL_PATTERN.findall(link.get("href", "")))
    emails.extend(EMAIL_PATTERN.findall(text))
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
    can_auto_qualify = bool(emails and vendor_signal and not is_aggregator)
    start_date = _date(structured.get("startDate"))
    if not start_date:
        date_node = soup.select_one('[itemprop="startDate"]')
        start_date = _date(date_node.get("content") or date_node.get_text(" ", strip=True)) if date_node else ""
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


def _brave_links(session, config):
    key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not key:
        return [], ["Broad web search is not configured: BRAVE_SEARCH_API_KEY is empty."]
    links = []
    errors = []
    for query in config["search_queries"]:
        try:
            response = session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": key},
                params={"q": query, "count": 10, "country": "us", "search_lang": "en"},
                timeout=20,
            )
            response.raise_for_status()
            links.extend(item.get("url", "") for item in response.json().get("web", {}).get("results", []))
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"Brave search '{query}': {exc}")
    return [url for url in dict.fromkeys(links) if url.startswith("http")], errors


def discover_events(session=None):
    session = session or requests.Session()
    config = _config()
    created = qualified = checked = 0
    errors = []
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
        event = Event(**data)
        db.session.add(event)
        created += 1
        qualified += event.status == "Qualified"
    state = db.session.get(AutomationState, "last_discovery_at") or AutomationState(key="last_discovery_at")
    state.value = datetime.now(timezone.utc).isoformat()
    db.session.add(state)
    db.session.commit()
    return {"checked": checked, "created": created, "qualified": qualified, "errors": errors}
