import re


def _first(pattern, text):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip(" .\n\r") if match else None


def parse_organizer_response(text):
    """Conservative, deterministic V1 extraction. Every result is reviewable."""
    updates = {}
    patterns = {
        "vendor_fee": r"(?:vendor|booth|space|food vendor) fee(?: is|:)?\s*\$?([\d,]+(?:\.\d{2})?)",
        "application_deadline": r"(?:application )?deadline(?: is|:)?\s*([^\n.]+)",
        "expected_attendance": r"(?:attendance|attendees)(?: is| was|:| of)?\s*(?:about |approximately )?([\d,]+(?:\+)?)",
        "operating_hours": r"(?:event |festival )?hours(?: are|:)?\s*([^\n.]+)",
        "food_vendor_count": r"(?:expect(?:ing)?|have|limit(?:ed)? to)\s*(\d+)\s+food vendors?",
        "application_url": r"(https?://[^\s<>\"]*(?:apply|application)[^\s<>\"]*)",
    }
    for field, pattern in patterns.items():
        value = _first(pattern, text)
        if value:
            updates[field] = f"${value}" if field == "vendor_fee" else value

    lowered = text.lower()
    application_open = any(
        phrase in lowered
        for phrase in (
            "applications are open",
            "applications are currently open",
            "application is open",
            "application is currently open",
            "now accepting applications",
        )
    )
    if application_open:
        updates["status"] = "Joe Action Required" if updates.get("application_url") else "Application Open"

    if any(phrase in lowered for phrase in (
        "not accepting applications", "not accepting vendors", "not accepting food vendors",
        "vendor applications are closed", "we are full", "no vendor spaces",
    )):
        updates["status"] = "Declined/Skip"
    elif any(phrase in lowered for phrase in (
        "applications are not open yet", "applications will open", "check back", "not open yet",
    )):
        updates["status"] = "Researching"

    permitted_products = []
    if "permit" in lowered or "allow" in lowered:
        if "cinnamon-glazed nuts" in lowered or "cinnamon glazed nuts" in lowered:
            permitted_products.append("Fresh cinnamon-glazed nuts permitted")
        if "gourmet popcorn" in lowered:
            permitted_products.append("Gourmet popcorn permitted")
    if permitted_products:
        updates["product_rules"] = "; ".join(permitted_products)

    danger_terms = ("zelle", "venmo", "cashapp", "cash app", "wire transfer", "banking", "w-9", "tax id", "sign the contract")
    flags = [term for term in danger_terms if term in lowered]
    material_requests = []
    if any(phrase in lowered for phrase in ("send your menu", "see your menu", "copy of your menu", "provide a menu", "menu and pricing")):
        material_requests.append("menu")
    if any(phrase in lowered for phrase in ("send photos", "send pictures", "product photos", "booth photos", "pictures of your", "photos of your")):
        material_requests.append("photos")
    return {
        "updates": updates,
        "flags": flags,
        "material_requests": material_requests,
        "needs_human_review": bool(flags) or application_open,
    }
