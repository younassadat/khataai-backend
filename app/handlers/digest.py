from datetime import date
from app.supabase_client import get_supabase
from app.handlers.ledger import get_month_totals, get_unpaid_debtors
from app.whatsapp import send_text


def _previous_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


async def send_digest_for_user(user_id: str, phone_number: str) -> None:
    year, month = _previous_month(date.today())
    income, expense = get_month_totals(user_id, year, month)
    net = income - expense
    debtors = get_unpaid_debtors(user_id)

    if debtors:
        names = ", ".join(f"{d['vendor']} (Rs. {d['amount']})" for d in debtors)
        debtor_line = f" Hisaab mein {len(debtors)} log hain: {names}."
    else:
        debtor_line = " Hisaab mein koi nahi hai."

    message = (
        f"Is mahine aapne Rs. {income} kamaye, Rs. {expense} kharch kiye. "
        f"Net: Rs. {net}.{debtor_line}"
    )
    await send_text(phone_number, message)


async def run_monthly_digest_for_all_active_users() -> int:
    """Called by Supabase pg_cron on the 1st of each month. Returns count sent."""
    supabase = get_supabase()
    users = (
        supabase.table("users").select("id, phone_number").eq("is_active", True).execute()
    ).data

    sent = 0
    for user in users:
        await send_digest_for_user(user["id"], user["phone_number"])
        sent += 1
    return sent
