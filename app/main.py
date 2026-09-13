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
    is_opt_in_reply,
    advance_to_business_name,
    save_business_name,
    save_business_type,
    WELCOME_MESSAGE,
    ASK_AGAIN_MESSAGE,
    ASK_BUSINESS_NAME,
    ASK_BUSINESS_TYPE,
    ONBOARDING_COMPLETE_MESSAGE,
)
from app.handlers.intent import classify, Intent, UNKNOWN_FALLBACK
from app.handlers.ledger import (
    save_ledger_entry,
    confirmation_message,
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
    return {"status": "ok", "service": "KhataAI", "provider": "meta"}


@app.post("/internal/run-digest")
async def run_digest(request: Request):
    from app.handlers.digest import run_monthly_digest_for_all_active_users
    secret = request.headers.get("x-cron-secret")
    if secret != os.environ.get("CRON_SECRET"):
        return Response(status_code=403)
    sent = await run_monthly_digest_for_all_active_users()
    return {"digests_sent": sent}


@app.get("/webhook")
def verify_webhook(request: Request):
    mode      = request.query_params.get("hub.mode")
    token     = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == os.environ["WHATSAPP_VERIFY_TOKEN"]:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive_message(request: Request):
    payload = await request.json()
    print(f"DEBUG RAW PAYLOAD: {payload}", flush=True)

    message, phone_number = _extract_message(payload)
    print(f"DEBUG extracted message={message}, phone={phone_number}", flush=True)
    if message is None:
        return Response(status_code=200)

    if not is_whitelisted(phone_number):
        print(f"DEBUG: {phone_number} not whitelisted", flush=True)
        await send_text(phone_number, REJECTION_MESSAGE)
        return Response(status_code=200)

    user, just_created = get_or_create_user(phone_number)
    print(f"DEBUG: user={user}, just_created={just_created}", flush=True)

    if not user["is_active"]:
        text = message.get("text", {}).get("body", "") if message["type"] == "text" else ""
        step = user.get("onboarding_step") or "awaiting_optin"

        if step == "awaiting_optin":
            if is_opt_in_reply(text):
                advance_to_business_name(phone_number)
                await send_text(phone_number, ASK_BUSINESS_NAME)
            elif just_created:
                await send_text(phone_number, WELCOME_MESSAGE)
            else:
                await send_text(phone_number, ASK_AGAIN_MESSAGE)
        elif step == "awaiting_business_name":
            save_business_name(phone_number, text)
            await send_text(phone_number, ASK_BUSINESS_TYPE)
        elif step == "awaiting_business_type":
            save_business_type(phone_number, text)
            await send_text(phone_number, ONBOARDING_COMPLETE_MESSAGE)

        return Response(status_code=200)

    message_type = message["type"]
    print(f"DEBUG: reached message_type={message_type}, phone={phone_number}", flush=True)
    if message_type in ("image", "audio") and not is_within_daily_limit(user["id"]):
        await send_text(phone_number, LIMIT_REACHED_MESSAGE)
        return Response(status_code=200)

    text_body = message.get("text", {}).get("body") if message_type == "text" else None
    intent    = classify(message_type, text_body)
    print(f"DEBUG: classified intent={intent}", flush=True)

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
        result = await send_text(phone_number, UNKNOWN_FALLBACK)
        print(f"DEBUG: fallback send_text result={result}", flush=True)

    return Response(status_code=200)


async def _handle_image_message(message: dict, phone_number: str, user_id: str) -> None:
    media_id = message["image"]["id"]
    caption  = message["image"].get("caption")
    await send_text(phone_number, "Receipt mil gayi! Abhi read kar raha hoon...")

    media_url = await get_media_url(media_id)
    if not media_url:
        await send_text(phone_number, FAILED_OCR_MESSAGE)
        return

    image_bytes = await download_media_bytes(media_url)
    if not image_bytes:
        await send_text(phone_number, FAILED_OCR_MESSAGE)
        return

    extracted = extract_receipt(image_bytes, caption=caption)
    if not extracted:
        await send_text(phone_number, FAILED_OCR_MESSAGE)
        return

    filename  = f"{media_id}.jpg"
    stored    = upload_receipt_image(user_id, filename, image_bytes, "image/jpeg")
    image_url = stored or media_url

    is_paid     = not extracted.get("is_udhaar", False)
    debtor_name = extracted.get("debtor_name") if not is_paid else None
    entry       = save_ledger_entry(
        user_id=user_id,
        extracted=extracted,
        image_url=image_url,
        raw_text=str(extracted),
        is_paid=is_paid,
        debtor_name=debtor_name,
    )
    increment_daily_count(user_id)
    await send_text(phone_number, confirmation_message(entry))


async def _handle_voice_message(message: dict, phone_number: str, user_id: str) -> None:
    media_id = message["audio"]["id"]
    await send_text(phone_number, "Voice note sun raha hoon...")

    media_url = await get_media_url(media_id)
    if not media_url:
        await send_text(phone_number, VOICE_FAILED_MESSAGE)
        return

    audio_bytes = await download_media_bytes(media_url)
    if not audio_bytes:
        await send_text(phone_number, VOICE_FAILED_MESSAGE)
        return

    result = transcribe_and_classify_voice(audio_bytes, mime_type="audio/ogg")
    if not result:
        await send_text(phone_number, VOICE_FAILED_MESSAGE)
        return

    intent = result.get("intent", "UNKNOWN")

    if intent == "RECEIPT":
        receipt = result.get("receipt")
        if not receipt or not receipt.get("amount"):
            await send_text(phone_number, VOICE_FAILED_MESSAGE)
            return
        extracted = {
            "date":   receipt.get("date"),
            "amount": receipt["amount"],
            "vendor": receipt.get("vendor") or "Unknown",
            "type":   receipt.get("type", "income"),
        }
        is_paid  = not receipt.get("is_udhaar", False)
        debtor_name = receipt.get("debtor_name") if not is_paid else None
        filename = f"{media_id}.ogg"
        stored   = upload_receipt_image(user_id, filename, audio_bytes, "audio/ogg")
        entry    = save_ledger_entry(
            user_id=user_id,
            extracted=extracted,
            image_url=stored or media_url,
            raw_text=result.get("transcription", ""),
            is_paid=is_paid,
            debtor_name=debtor_name,
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


def _extract_message(payload: dict):
    try:
        value    = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            print(f"DEBUG _extract_message: no 'messages' key, value={value}", flush=True)
            return None, None
        message      = messages[0]
        phone_number = "+" + message["from"]
        return message, phone_number
    except (KeyError, IndexError) as e:
        print(f"DEBUG _extract_message EXCEPTION: {e}, payload={payload}", flush=True)
        return None, None
