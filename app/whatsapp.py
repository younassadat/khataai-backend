"""
KhataAI — WhatsApp helper (Green API version)
Owner: Younas

Replaces the Meta Cloud API version.
Green API lets us use a regular WhatsApp number with no Meta
business verification required — perfect for beta testing.

Environment variables needed:
    GREEN_API_INSTANCE_ID   — your instance ID from console.green-api.com
    GREEN_API_TOKEN         — your API token from console.green-api.com

Green API docs: https://green-api.com/en/docs/
"""

import os
import logging
import httpx

logger = logging.getLogger("khataai.whatsapp")

GREEN_API_BASE = os.environ.get(
    "GREEN_API_URL",
    "https://7107.api.greenapi.com"
).rstrip("/")


def _instance_id() -> str:
    return os.environ["GREEN_API_INSTANCE_ID"]


def _token() -> str:
    return os.environ["GREEN_API_TOKEN"]


def _base() -> str:
    return f"{GREEN_API_BASE}/waInstance{_instance_id()}"


def _format_phone(phone: str) -> str:
    """
    Green API expects phone numbers in the format: 923001234567@c.us
    Input can be +923001234567 or 923001234567 — we normalise both.
    """
    # Strip leading + if present
    number = phone.lstrip("+")
    # Green API chat ID format
    return f"{number}@c.us"


async def send_text(to: str, body: str) -> bool:
    """
    Send a plain text WhatsApp message to a phone number.
    Returns True on success, False on failure.
    Never raises — webhook must always return 200.
    """
    url = f"{_base()}/sendMessage/{_token()}"
    payload = {
        "chatId": _format_phone(to),
        "message": body,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload)
            logger.info(
                "GREEN API SEND: status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error(
            "GREEN API ERROR: status=%s body=%s",
            e.response.status_code,
            e.response.text,
            exc_info=True,
        )
        return False
    except Exception as e:
        logger.error("send_text failed to %s: %s", to, e, exc_info=True)
        return False


async def get_media_url(media_id: str) -> str | None:
    """
    Green API includes the media download URL directly in the webhook
    payload — no separate API call needed like Meta requires.

    For Green API, media_id IS the download URL already.
    We return it as-is.
    """
    # In Green API webhook payloads, we pass the downloadUrl directly
    # as the media_id. So just return it.
    return media_id if media_id else None


async def download_media_bytes(media_url: str) -> bytes | None:
    """
    Download media (image/audio) from Green API's CDN.
    Green API URLs are publicly accessible — no auth header needed.
    Returns raw bytes, or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(media_url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.error("download_media_bytes failed: %s", e)
        return None
