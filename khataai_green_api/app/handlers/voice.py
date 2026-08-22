"""
Phase 3 — Voice note support.

Pakistani sellers use WhatsApp voice notes constantly — faster than typing
Urdu on a phone keyboard. A seller who would never type out a receipt will
happily send a 10-second voice note: "Sana se 2,500 mila, dupatta wala".

Flow:
  WhatsApp audio message
    → download bytes from Meta CDN (same as image flow)
    → send to Gemini 1.5 Flash (handles audio natively)
    → Gemini transcribes + classifies intent in ONE call
    → route to existing intent handlers — no new handlers needed.
"""

from google import genai
from google.genai import types
from app.gemini_client import _get_client, _model_name

VOICE_PROMPT = (
    "This is a WhatsApp voice note from a Pakistani small business seller. "
    "The seller speaks in Urdu, Roman Urdu, or mixed Urdu/English. "
    "Do the following in one response:\n\n"
    "1. Transcribe the voice note.\n"
    "2. Classify the intent into ONE of these categories:\n"
    "   - RECEIPT: the seller is recording a payment received or expense made "
    "     (extract amount in PKR, vendor/customer name, date if mentioned, "
    "     and whether it is income or expense)\n"
    "   - EARNINGS_QUERY: the seller is asking how much they earned or what "
    "     their profit is\n"
    "   - DEBTOR_QUERY: the seller is asking who still owes them money\n"
    "   - UNKNOWN: anything else\n\n"
    "Return JSON only, no explanation, no markdown fences. Format:\n"
    '{"intent": "RECEIPT|EARNINGS_QUERY|DEBTOR_QUERY|UNKNOWN", '
    '"transcription": "string", '
    '"receipt": {"amount": number, "vendor": "string", "type": "income|expense", '
    '"date": "YYYY-MM-DD or null", "is_udhaar": false}}'
    "\n\nFor non-RECEIPT intents, set receipt to null."
)

VOICE_FAILED_MESSAGE = (
    "Voice note sun nahi paya. Kya aap dobara bhejain ya text mein likhain?"
)


def transcribe_and_classify_voice(audio_bytes: bytes, mime_type: str = "audio/ogg") -> dict | None:
    """
    Sends a voice note to Gemini for transcription + intent classification.

    Returns a dict with keys: intent, transcription, receipt (or None on failure).

    mime_type: WhatsApp voice notes are typically audio/ogg (opus codec).
    Gemini 1.5 Flash accepts ogg, mp4, wav, mp3, aiff, flac, and webm.
    """
    import json
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=_model_name(),
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                VOICE_PROMPT,
            ],
        )
        raw = response.text.strip()
        # Strip markdown fences defensively (same as extract_receipt)
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json\n", "", 1).replace("json", "", 1)
        data = json.loads(raw)
        if "intent" not in data:
            return None
        return data
    except Exception:
        return None
