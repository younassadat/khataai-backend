import os
import json
from google import genai
from google.genai import types

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")


OCR_PROMPT = (
    "Extract date, amount (in PKR), vendor name, and whether this is income "
    "or expense from this receipt image. Return JSON only, no explanation, "
    "no markdown fences. Format: "
    '{"date": "YYYY-MM-DD", "amount": number, "vendor": "string", "type": "income|expense"}. '
    "If a field cannot be determined, use null for that field."
)


def extract_receipt(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict | None:
    """Send a receipt photo to Gemini and parse the structured JSON response.

    Returns None if extraction or parsing failed (caller sends the
    'samajh nahi aaya' fallback in that case).
    """
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=_model_name(),
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                OCR_PROMPT,
            ],
        )
        raw = response.text.strip()
        # Gemini sometimes wraps JSON in ```json ... ``` fences despite instructions.
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json\n", "", 1).replace("json", "", 1)
        data = json.loads(raw)
        if not data.get("amount") or not data.get("type"):
            return None
        return data
    except Exception:
        return None


def answer_ledger_question(question_urdu: str, income_total: float, expense_total: float, month_label: str) -> str:
    """Turn real ledger numbers into a natural Urdu reply. Never lets the model invent numbers."""
    client = _get_client()
    prompt = (
        "You are KhataAI, a friendly bookkeeping assistant for a Pakistani "
        "small business seller. Reply ONLY in Urdu (Roman Urdu is fine, "
        "matching the user's style), in 1-3 short sentences. Use ONLY the "
        "numbers given below — never invent or estimate figures.\n\n"
        f"Month: {month_label}\n"
        f"Total income: Rs. {income_total}\n"
        f"Total expenses: Rs. {expense_total}\n"
        f"Net: Rs. {income_total - expense_total}\n\n"
        f"User's question: {question_urdu}"
    )
    response = client.models.generate_content(model=_model_name(), contents=prompt)
    return response.text.strip()
