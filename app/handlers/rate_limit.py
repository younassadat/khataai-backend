"""
Phase 1 — API rate limiting.

Prevents a single beta user from draining Gemini API credits.
Each user gets DAILY_LIMIT receipt scans per day. The counter resets
at midnight UTC via the pg_cron job defined in schema.sql.

This check runs immediately after the whitelist check and before
any AI or ledger logic.
"""

import os
from app.supabase_client import get_supabase

# Configurable via env var — default 20 receipts/day for beta users.
DAILY_LIMIT = int(os.environ.get("DAILY_RECEIPT_LIMIT", 20))

LIMIT_REACHED_MESSAGE = (
    "Aap ne aaj ki limit ({limit} receipts) use kar li. "
    "Kal subah reset ho jaye gi. Shukriya!"
).format(limit=DAILY_LIMIT)


def is_within_daily_limit(user_id: str) -> bool:
    """
    Returns True if the user has NOT yet hit their daily receipt cap.
    Returns False if they have — caller should send LIMIT_REACHED_MESSAGE.
    """
    supabase = get_supabase()
    result = (
        supabase.table("users")
        .select("daily_message_count")
        .eq("id", user_id)
        .single()
        .execute()
    )
    count = result.data.get("daily_message_count", 0) or 0
    return count < DAILY_LIMIT


def increment_daily_count(user_id: str) -> None:
    """
    Increments the user's daily receipt counter by 1.
    Call this AFTER a receipt is successfully processed.
    """
    supabase = get_supabase()
    # Use Postgres RPC to do an atomic increment so concurrent requests
    # don't race each other.
    supabase.rpc(
        "increment_daily_count",
        {"target_user_id": user_id},
    ).execute()
