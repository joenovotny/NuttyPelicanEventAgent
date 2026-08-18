import re

BLOCKED_ACTIONS = (
    "submit an application",
    "send or authorize a payment",
    "accept terms or sign a contract",
    "share banking, tax, identity, or other sensitive information",
    "commit The Nutty Pelican to attendance",
)

_DANGEROUS_PATTERNS = {
    "payment or money transfer": r"\b(pay|payment|zelle|venmo|cash\s?app|wire|bank transfer|credit card)\b",
    "contract or binding acceptance": r"\b(sign|signature|agree to|accept (the )?terms|contract)\b",
    "sensitive information": r"\b(ssn|social security|ein|tax id|routing number|bank account|w-?9)\b",
    "application submission": r"\b(submit|complete) (the |your )?(vendor )?application\b",
}


class GuardrailViolation(ValueError):
    pass


def validate_outbound(body):
    """Reject messages that appear to authorize a protected action."""
    lowered = body.lower()
    lowered = lowered.replace(
        "joe will personally review and complete any application, agreement, or payment.",
        "",
    )
    safe_context = ("please send", "could you provide", "what is", "do you require")
    for label, pattern in _DANGEROUS_PATTERNS.items():
        if re.search(pattern, lowered) and not any(term in lowered for term in safe_context):
            raise GuardrailViolation(
                f"Blocked: the draft may involve {label}. Joe must handle this action."
            )
