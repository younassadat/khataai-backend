import os
import logging
import httpx

logger = logging.getLogger("khataai.whatsapp")

API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v20.0")


def _base_url() -> str:
    phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    return f"https://graph.facebook.com/{API_VERSION}/{phone_id}"


def _headers() -> dict:
    token = os.environ["WHATSAPP_TOKEN"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def send_text(to: str, body: str) -> bool:
    """Send a plain text WhatsApp message back to a user.

    Returns True on success, False on failure. Never raises — if Meta is
    down or rate-limiting us, the webhook must still return 200 to Meta,
    otherwise Meta will keep retrying the original inbound message and we
    end up processing it multiple times.
    """
    url = f"{_base_url()}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=_headers())
            resp.raise_for_status()
        return True
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.error("Failed to send WhatsApp message to %s: %s", to, e)
        return False


async def get_media_url(media_id: str) -> str | None:
    """Step 1 of media download: media_id -> temporary CDN URL. Returns None on failure."""
    token = os.environ["WHATSAPP_TOKEN"]
    url = f"https://graph.facebook.com/{API_VERSION}/{media_id}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()["url"]
    except (httpx.HTTPError, httpx.TimeoutException, KeyError) as e:
        logger.error("Failed to resolve media URL for %s: %s", media_id, e)
        return None


async def download_media_bytes(media_url: str) -> bytes | None:
    """Step 2 of media download: fetch the actual image bytes from the CDN URL. Returns None on failure."""
    token = os.environ["WHATSAPP_TOKEN"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(media_url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.content
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.error("Failed to download media from %s: %s", media_url, e)
        return None
