from app.supabase_client import get_supabase

REJECTION_MESSAGE = (
    "KhataAI abhi sirf invited beta users ke liye available hai. "
    "Beta access ke liye humse contact karein."
)


def is_whitelisted(phone_number: str) -> bool:
    """Check beta_users table. This must run before any AI/ledger/onboarding logic."""
    supabase = get_supabase()
    result = (
        supabase.table("beta_users")
        .select("phone_number")
        .eq("phone_number", phone_number)
        .execute()
    )
    return len(result.data) > 0
