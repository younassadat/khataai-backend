from enum import Enum

DEBTOR_KEYWORDS = ["hisaab mein", "kaun hisaab", "udhaar", "baqaya"]
EARNINGS_KEYWORDS = ["kitna kamaya", "kya hua", "is mahine", "kamaya", "kharch"]
DIGEST_TRIGGER = "digest"


class Intent(str, Enum):
    IMAGE = "image"
    VOICE = "voice"           # Phase 3: voice note support
    DEBTOR_QUERY = "debtor_query"
    EARNINGS_QUERY = "earnings_query"
    MANUAL_DIGEST = "manual_digest"
    UNKNOWN = "unknown"


def classify(message_type: str, text: str | None) -> Intent:
    """message_type is the WhatsApp payload type: 'image', 'audio', 'text', etc."""
    if message_type == "image":
        return Intent.IMAGE

    # Phase 3: WhatsApp voice notes arrive as type 'audio'
    if message_type == "audio":
        return Intent.VOICE

    if not text:
        return Intent.UNKNOWN

    lowered = text.strip().lower()

    if lowered == DIGEST_TRIGGER:
        return Intent.MANUAL_DIGEST
    if any(kw in lowered for kw in DEBTOR_KEYWORDS):
        return Intent.DEBTOR_QUERY
    if any(kw in lowered for kw in EARNINGS_KEYWORDS):
        return Intent.EARNINGS_QUERY
    return Intent.UNKNOWN


UNKNOWN_FALLBACK = (
    "Mujhe samajh nahi aaya. Kya aap receipt bhej sakte hain, receipt ki "
    "voice note bhej sakte hain, ya poochh sakte hain: is mahine kitna kamaya?"
)
