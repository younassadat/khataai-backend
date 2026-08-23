"""
KhataAI — Gemini Client (Demo-safe version)
Uses simple Urdu templates for text queries — no Gemini needed.
Only uses Gemini for receipt OCR (image processing).
"""

import os
import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("khataai.gemini")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _model_name():
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite")


OCR_PROMPT = (
    "Extract information from this receipt image. "
    "Return JSON only, no explanation, no markdown fences. "
    'Format: {"date": "YYYY-MM-DD", "amount": number, "vendor": "string", "type": "income|expense"}. '
    "If a field cannot be determined use null. "
    "amount must be a number in PKR with no currency symbol. "
    "type is income if money was received, expense if money was paid out."
)


def extract_receipt(image_bytes: bytes, mime_type: str = "image/jpeg"):
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
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json\n", "", 1).replace("json", "", 1).strip()
        data = json.loads(raw)
        if not data.get("amount") or not data.get("type"):
            return None
        return data
    except Exception as e:
        logger.error("Gemini OCR failed: %s", e)
        return None


def answer_ledger_question(question: str, income: float, expense: float, month: str) -> str:
    """
    Simple Urdu template — no Gemini needed for text queries.
    Faster, more reliable, zero API cost.
    """
    if income == 0.0 and expense == 0.0:
        return (
            f"{month} mein abhi tak koi receipt save nahi hui. "
            "Receipt ki photo bhejein aur main hisaab rakhna shuru kar deta hoon!"
        )

    net = income - expense

    if net > 0:
        closing = "Bohat acha! Allah aapke rizq mein barkat de."
    elif net == 0:
        closing = "Is baar income aur kharch barabar rahe."
    else:
        closing = "Is mahine thoda mushkil raha — himmat rakhein!"

    return (
        f"{month} ka hisaab:\n\n"
        f"Kamaya:  Rs. {income:,.0f}\n"
        f"Kharch:  Rs. {expense:,.0f}\n"
        f"Net:     Rs. {net:,.0f}\n\n"
        f"{closing}"
    )
