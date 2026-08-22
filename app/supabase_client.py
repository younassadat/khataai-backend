import os
import logging
from supabase import create_client, Client

logger = logging.getLogger("khataai.supabase")

_supabase: Client | None = None

RECEIPTS_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "receipts")
# 10 years — a private bucket needs a signed URL, and this app has no
# "view my receipt" feature yet, so a very long expiry is the pragmatic
# choice over re-signing URLs on every read.
SIGNED_URL_TTL_SECONDS = 60 * 60 * 24 * 365 * 10


def get_supabase() -> Client:
    """Lazy singleton so we don't reconnect on every request."""
    global _supabase
    if _supabase is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _supabase = create_client(url, key)
    return _supabase


def upload_receipt_image(user_id: str, filename: str, data: bytes, mime_type: str) -> str | None:
    """Uploads a receipt image to Supabase Storage and returns a long-lived
    signed URL. Returns None on failure — caller should fall back to storing
    whatever URL it already has (e.g. the temporary Meta CDN one) rather
    than losing the receipt data entirely.
    """
    supabase = get_supabase()
    path = f"{user_id}/{filename}"
    try:
        supabase.storage.from_(RECEIPTS_BUCKET).upload(
            path, data, {"content-type": mime_type}
        )
    except Exception as e:
        logger.error("Failed to upload receipt image to storage: %s", e)
        return None

    try:
        signed = supabase.storage.from_(RECEIPTS_BUCKET).create_signed_url(
            path, SIGNED_URL_TTL_SECONDS
        )
        return signed.get("signedURL") or signed.get("signedUrl")
    except Exception as e:
        logger.error("Uploaded receipt but failed to sign URL: %s", e)
        return path  # at least the object exists and is findable by path
