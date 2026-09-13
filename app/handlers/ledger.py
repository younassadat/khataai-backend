from datetime import date, datetime
from app.supabase_client import get_supabase

FAILED_OCR_MESSAGE = (
    "Maafi chahta hoon, yeh receipt samajh nahi aaya. Kya aap dobara bhej sakte hain?"
)

# Decision (v2): a Pakistani shopkeeper who doesn't know "trigger words" will
# just describe the sale naturally — "ye udhaar hai Ahmed Bhai ka", "abhi paise
# nahi diye", etc. Gemini reads the caption alongside the receipt image (see
# gemini_client.extract_receipt) and returns is_udhaar + debtor_name directly,
# using real language understanding instead of keyword matching.


def save_ledger_entry(
    user_id: str,
    extracted: dict,
    image_url: str,
    raw_text: str,
    is_paid: bool = True,
    debtor_name: str | None = None,
) -> dict:
    supabase = get_supabase()
    row = {
        "user_id": user_id,
        "date": extracted.get("date") or str(date.today()),
        "amount": extracted["amount"],
        "vendor": extracted.get("vendor") or "Unknown",
        "type": extracted["type"],
        "image_url": image_url,
        "raw_text": raw_text,
        "is_paid": is_paid,
        "debtor_name": debtor_name,
    }
    result = supabase.table("ledger_entries").insert(row).execute()
    return result.data[0]


def confirmation_message(entry: dict) -> str:
    base = f"Receipt save ho gayi: Rs. {entry['amount']} {entry['vendor']} ✓"
    if not entry.get("is_paid", True):
        base += " (Udhaar mein add ho gaya)"
    return base


def get_month_totals(user_id: str, year: int, month: int) -> tuple[float, float]:
    """Returns (income_total, expense_total) for the given user/month."""
    supabase = get_supabase()
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    rows = (
        supabase.table("ledger_entries")
        .select("amount, type")
        .eq("user_id", user_id)
        .gte("date", str(start))
        .lt("date", str(end))
        .execute()
        .data
    )
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    return income, expense


def get_unpaid_debtors(user_id: str) -> list[dict]:
    supabase = get_supabase()
    rows = (
        supabase.table("ledger_entries")
        .select("vendor, amount, debtor_name")
        .eq("user_id", user_id)
        .eq("is_paid", False)
        .execute()
        .data
    )
    return rows


def format_debtor_list(rows: list[dict]) -> str:
    if not rows:
        return "Abhi koi hisaab mein nahi hai. Sab clear hai! ✓"
    lines = [f"- {r.get('debtor_name') or r['vendor']}: Rs. {r['amount']}" for r in rows]
    return "Hisaab mein yeh log hain:\n" + "\n".join(lines)


def mark_debtor_paid(user_id: str, name: str) -> bool:
    """Marks the most specific matching unpaid entry as paid. Tries debtor_name
    first (the real customer name), falls back to vendor for older entries
    saved before debtor_name existed. Returns True if anything was updated."""
    supabase = get_supabase()
    pattern = f"%{name.strip()}%"

    result = (
        supabase.table("ledger_entries")
        .update({"is_paid": True})
        .eq("user_id", user_id)
        .eq("is_paid", False)
        .ilike("debtor_name", pattern)
        .execute()
    )
    if result.data:
        return True

    result = (
        supabase.table("ledger_entries")
        .update({"is_paid": True})
        .eq("user_id", user_id)
        .eq("is_paid", False)
        .ilike("vendor", pattern)
        .execute()
    )
    return bool(result.data)
