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


CONVERSATIONAL_PROMPT_TEMPLATE = (
    "You are KhataAI, a WhatsApp bookkeeping assistant for small Pakistani "
    "shopkeepers and social-media sellers. It replies briefly in casual Roman "
    "Urdu (mixed with a little English), the way the seller itself writes.\n\n"
    "The seller just sent this message. It didn't match a receipt, and it "
    "wasn't caught by a simple keyword check for earnings, the debtor list, "
    "or the monthly digest — but it might still genuinely be one of those, "
    "just phrased with a typo or informally, e.g. 'kon hisab me h', 'kitna "
    "kamaya is mahine', 'kitna banta h abhi tak':\n"
    "\"{text}\"\n\n"
    "Return JSON only, no explanation, no markdown fences. Format:\n"
    '{{"intent": "MARK_PAID|DEBTOR_QUERY|EARNINGS_QUERY|GREETING|THANKS|HELP|CHITCHAT|UNCLEAR", '
    '"debtor_name": "string or null", "reply": "string or null"}}\n\n'
    "MARK_PAID — the seller is saying a specific customer or store has now "
    "paid off their udhaar (credit), e.g. 'Ahmed Bhai ne paisay de diye', "
    "'ABC store ka hisaab clear kar do', 'Ahmed ne udhaar chuka diya', "
    "'usne payment kar di'. Put the customer/store name in debtor_name. "
    "Leave reply as null for this one.\n"
    "DEBTOR_QUERY — asking who still owes money / who's in the udhaar list, "
    "even with typos like 'kon hisab me h' or 'kis ka udhaar baki hai'. "
    "Leave reply and debtor_name null.\n"
    "EARNINGS_QUERY — asking how much they earned/spent this month, even "
    "informally, e.g. 'is mahine ka hisaab', 'kitna banta hai abhi tak'. "
    "Leave reply and debtor_name null.\n"
    "GREETING — hi / hello / salam / assalamualaikum and similar.\n"
    "THANKS — shukriya / thanks / thank you and similar.\n"
    "HELP — asking what KhataAI does, how to use it, or what it can do.\n"
    "CHITCHAT — small talk or a general question unrelated to bookkeeping.\n"
    "UNCLEAR — anything else that doesn't fit any of the above.\n\n"
    "For GREETING, THANKS, HELP, CHITCHAT, and UNCLEAR: write a short (1-2 "
    "sentence) natural reply in casual Roman Urdu in the 'reply' field, "
    "matching KhataAI's warm, simple voice. For HELP specifically, briefly "
    "mention: seller can send a receipt photo or voice note to log a sale or "
    "purchase, just mention naturally if it's udhaar (credit) and who owes, "
    "ask 'kitna kamaya' for earnings, ask 'kaun hisaab mein hai' for the "
    "debtor list, or say 'digest' for a monthly summary. Leave debtor_name "
    "null for all of these."
)


def classify_conversational(text: str) -> dict:
    """Fallback for anything that isn't a receipt or a cheap-keyword match
    (digest/debtor/earnings). Covers everyday chat naturally instead of
    needing an ever-growing hardcoded phrase list."""
    fallback = {"intent": "UNCLEAR", "debtor_name": None, "reply": None}
    try:
        client = _get_client()
        prompt = CONVERSATIONAL_PROMPT_TEMPLATE.format(text=text)
        response = client.models.generate_content(model=_model_name(), contents=[prompt])
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json\n", "", 1).replace("json", "", 1).strip()
        data = json.loads(raw)
        return {**fallback, **data}
    except Exception as e:
        logger.error("Gemini conversational classification failed: %s", e)
        return fallback
