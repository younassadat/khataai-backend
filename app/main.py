import os
from datetime import datetime
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv

from app.whatsapp import send_text, get_media_url, download_media_bytes
from app.gemini_client import extract_receipt, answer_ledger_question
from app.supabase_client import get_supabase, upload_receipt_image
from app.handlers.whitelist import is_whitelisted, REJECTION_MESSAGE
from app.handlers.rate_limit import is_within_daily_limit, increment_daily_count, LIMIT_REACHED_MESSAGE
from app.handlers.onboarding import (
    get_or_create_user,
    activate_user,
    is_opt_in_reply,
    WELCOME_MESSAGE,
    ASK_AGAIN_MESSAGE,
)
from app.handlers.intent import classify, Intent, UNKNOWN_FALLBACK
from app.handlers.ledger import (
    save_ledger_entry,
    confirmation_message,
    determine_is_paid,
    get_month_totals,
    get_unpaid_debtors,
    format_debtor_list,
    FAILED_OCR_MESSAGE,
)
from app.handlers.voice import transcribe_and_classify_voice, VOICE_FAILED_MESSAGE
from app.handlers.digest import send_digest_for_user

load_dotenv()

app = FastAPI(title="KhataAI")


@app.get("/")
def health():
    return {"status": "ok", "service": "KhataAI"}


# ---------------------------------------------------------------------------
# Phase 4: cron target — monthly digest
# ---------------------------------------------------------------------------
@app.post("/internal/run-digest")
async def run_digest(request: Request):
    from app.handlers.digest import run_monthly_digest_for_all_active_users

    secret = request.headers.get("x-cron-secret")
    if secret != os.environ.get("CRON_SECRET"):
        return Response(status_code=403)

    sent = await run_monthly_digest_for_all_active_users()
    return {"digests_sent": sent}


# ---------------------------------------------------------------------------
# Phase 1: webhook verification
# ---------------------------------------------------------------------------
@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    expected_token = os.environ["WHATSAPP_VERIFY_TOKEN"]
    if mode == "subscribe" and token == expected_token:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


# ---------------------------------------------------------------------------
# Phase 1–5: incoming message handler
# ---------------------------------------------------------------------------
@app.post("/webhook")
async def receive_message(request: Request):
    payload = await request.json()

    message, phone_number = _extract_message(payload)
    if message is None:
        return Response(status_code=200)

    # --- FIRST CHECK: beta whitelist (Phase 1) ---
    if not is_whitelisted(phone_number):
        await send_text(phone_number, REJECTION_MESSAGE)
        return Response(status_code=200)

    user, just_created = get_or_create_user(phone_number)

    # --- Onboarding gate (Phase 5): nothing else runs until opted in ---
    if not user["is_active"]:
        text = message.get("text", {}).get("body", "") if message["type"] == "text" else ""
        if is_opt_in_reply(text):
            activate_user(phone_number)
            await send_text(phone_number, "Shukriya! Ab aap receipts bhej sakte hain.")
        elif just_created:
            await send_text(phone_number, WELCOME_MESSAGE)
        else:
            await send_text(phone_number, ASK_AGAIN_MESSAGE)
        return Response(status_code=200)

    # --- SECOND CHECK: daily rate limit (Phase 1) ---
    # Only applied to AI-heavy operations (receipt scan + voice note).
    # Text queries (earnings, debtors) are cheap and not rate-limited.
    message_type = message["type"]
    if message_type in ("image", "audio") and not is_within_daily_limit(user["id"]):
        await send_text(phone_number, LIMIT_REACHED_MESSAGE)
        return Response(status_code=200)

    # --- Intent routing (Phase 3) ---
    text_body = message.get("text", {}).get("body") if message_type == "text" else None
    intent = classify(message_type, text_body)

    if intent == Intent.IMAGE:
        await _handle_image_message(message, phone_number, user["id"])

    elif intent == Intent.VOICE:
        await _handle_voice_message(message, phone_number, user["id"])

    elif intent == Intent.MANUAL_DIGEST:
        await send_digest_for_user(user["id"], phone_number)

    elif intent == Intent.DEBTOR_QUERY:
        debtors = get_unpaid_debtors(user["id"])
        await send_text(phone_number, format_debtor_list(debtors))

    elif intent == Intent.EARNINGS_QUERY:
        now = datetime.utcnow()
        income, expense = get_month_totals(user["id"], now.year, now.month)
        reply = answer_ledger_question(text_body, income, expense, now.strftime("%B"))
        await send_text(phone_number, reply)

    else:
        await send_text(phone_number, UNKNOWN_FALLBACK)

    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Phase 2: receipt image handler
# ---------------------------------------------------------------------------
async def _handle_image_message(message: dict, phone_number: str, user_id: str) -> None:
    media_id = message["image"]["id"]
    caption = message["image"].get("caption")
    await send_text(phone_number, "Received! Processing...")

    media_url = await get_media_url(media_id)
    if media_url is None:
        await send_text(phone_number, FAILED_OCR_MESSAGE)
        return

    image_bytes = await download_media_bytes(media_url)
    if image_bytes is None:
        await send_text(phone_number, FAILED_OCR_MESSAGE)
        return

    extracted = extract_receipt(image_bytes)
    if extracted is None:
        await send_text(phone_number, FAILED_OCR_MESSAGE)
        return

    filename = f"{media_id}.jpg"
    stored_url = upload_receipt_image(user_id, filename, image_bytes, "image/jpeg")
    image_url = stored_url or media_url

    is_paid = determine_is_paid(caption)
    entry = save_ledger_entry(
        user_id=user_id,
        extracted=extracted,
        image_url=image_url,
        raw_text=str(extracted),
        is_paid=is_paid,
    )
    # Increment rate limit counter after successful processing
    increment_daily_count(user_id)
    await send_text(phone_number, confirmation_message(entry))


# ---------------------------------------------------------------------------
# Phase 3: voice note handler
# ---------------------------------------------------------------------------
async def _handle_voice_message(message: dict, phone_number: str, user_id: str) -> None:
    """
    Downloads the voice note from Meta CDN, sends to Gemini for
    transcription + intent classification, then routes to the appropriate
    handler — same handlers used for text and image messages.
    """
    media_id = message["audio"]["id"]
    await send_text(phone_number, "Voice note sun raha hoon...")

    media_url = await get_media_url(media_id)
    if media_url is None:
        await send_text(phone_number, VOICE_FAILED_MESSAGE)
        return

    audio_bytes = await download_media_bytes(media_url)
    if audio_bytes is None:
        await send_text(phone_number, VOICE_FAILED_MESSAGE)
        return

    # WhatsApp voice notes are OGG/Opus. Gemini 1.5 Flash supports this natively.
    result = transcribe_and_classify_voice(audio_bytes, mime_type="audio/ogg")
    if result is None:
        await send_text(phone_number, VOICE_FAILED_MESSAGE)
        return

    intent = result.get("intent", "UNKNOWN")

    if intent == "RECEIPT":
        receipt = result.get("receipt")
        if not receipt or not receipt.get("amount"):
            await send_text(phone_number, VOICE_FAILED_MESSAGE)
            return

        # Build an extracted dict matching what extract_receipt() returns
        extracted = {
            "date": receipt.get("date"),
            "amount": receipt["amount"],
            "vendor": receipt.get("vendor") or "Unknown",
            "type": receipt.get("type", "income"),
        }

        # Treat "is_udhaar" from voice classification as the unpaid flag
        is_paid = not receipt.get("is_udhaar", False)

        filename = f"{media_id}.ogg"
        stored_url = upload_receipt_image(user_id, filename, audio_bytes, "audio/ogg")
        audio_url = stored_url or media_url

        entry = save_ledger_entry(
            user_id=user_id,
            extracted=extracted,
            image_url=audio_url,
            raw_text=result.get("transcription", ""),
            is_paid=is_paid,
        )
        increment_daily_count(user_id)
        await send_text(phone_number, confirmation_message(entry))

    elif intent == "EARNINGS_QUERY":
        now = datetime.utcnow()
        income, expense = get_month_totals(user_id, now.year, now.month)
        reply = answer_ledger_question(
            result.get("transcription", "is mahine kitna kamaya?"),
            income, expense, now.strftime("%B")
        )
        await send_text(phone_number, reply)

    elif intent == "DEBTOR_QUERY":
        debtors = get_unpaid_debtors(user_id)
        await send_text(phone_number, format_debtor_list(debtors))

    else:
        await send_text(phone_number, UNKNOWN_FALLBACK)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _extract_message(payload: dict):
    """Pulls the first inbound message + sender number out of a WhatsApp
    webhook payload, or (None, None) if this payload has no message."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None, None
        message = messages[0]
        phone_number = message["from"]
        return message, phone_number
    except (KeyError, IndexError):
        return None, None
