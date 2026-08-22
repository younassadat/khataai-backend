from datetime import date, datetime
from app.supabase_client import get_supabase

FAILED_OCR_MESSAGE = (
    "Maafi chahta hoon, yeh receipt samajh nahi aaya. Kya aap dobara bhej sakte hain?"
)

# Decision: the guide doesn't specify how a receipt gets flagged as unpaid,
# so the rule is a caption keyword — the seller types "udhaar" (or similar)
# in the WhatsApp image caption when forwarding a receipt for an unpaid
# invoice. Everything else defaults to paid. Simple, matches the guide's
# "no complex NLP" philosophy, and the seller controls it directly.
UNPAID_KEYWORDS = ["udhaar", "baqaya", "unpaid", "credit pe"]


def determine_is_paid(caption: str | None) -> bool:
    if not caption:
        return True
    lowered = caption.strip().lower()
    return not any(kw in lowered for kw in UNPAID_KEYWORDS)


def save_ledger_entry(user_id: str, extracted: dict, image_url: str, raw_text: str, is_paid: bool = True) -> dict:
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
        .select("vendor, amount")
        .eq("user_id", user_id)
        .eq("is_paid", False)
        .execute()
        .data
    )
    return rows


def format_debtor_list(rows: list[dict]) -> str:
    if not rows:
        return "Abhi koi hisaab mein nahi hai. Sab clear hai! ✓"
    lines = [f"- {r['vendor']}: Rs. {r['amount']}" for r in rows]
    return "Hisaab mein yeh log hain:\n" + "\n".join(lines)
