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


OCR_PROMPT_TEMPLATE = (
    "Extract information from this receipt image. The seller sent this WhatsApp "
    "caption along with the photo (it may be empty): \"{caption}\"\n\n"
    "Return JSON only, no explanation, no markdown fences. Format:\n"
    '{{"date": "YYYY-MM-DD", "amount": number, "vendor": "string", '
    '"type": "income|expense", "is_udhaar": true|false, "debtor_name": "string or null"}}\n\n'
    "is_udhaar is true if the caption indicates this was sold on credit and "
    "payment is still pending. Sellers write this in all kinds of natural Urdu, "
    "Roman Urdu, or English phrasing, not fixed keywords, e.g. 'udhaar', "
    "'baqaya', 'abhi paise nahi mile', 'ye udhaar hai Ahmed Bhai ka', 'credit pe "
    "diya', 'payment pending hai'. Use your understanding of the sentence, not "
    "exact word matching. "
    "debtor_name is the name of the customer who owes the money, extracted from "
    "the caption if mentioned anywhere in it. If it isn't a credit sale, or no "
    "name is given, debtor_name should be null. "
    "If any field cannot be determined use null. "
    "amount must be a number in PKR with no currency symbol. "
    "type is income if money was received, expense if money was paid out."
)


def extract_receipt(image_bytes: bytes, mime_type: str = "image/jpeg", caption: str | None = None):
    try:
        client = _get_client()
        prompt = OCR_PROMPT_TEMPLATE.format(caption=caption or "")
        response = client.models.generate_content(
            model=_model_name(),
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
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
