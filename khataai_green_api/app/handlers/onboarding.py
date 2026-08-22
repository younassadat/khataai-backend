from app.supabase_client import get_supabase

WELCOME_MESSAGE = (
    "Assalam o Alaikum! Main KhataAI hoon — aapka AI bookkeeper. Main aapke "
    "receipts aur invoices read karke aapka hisaab rakhta hoon.\n\n"
    "Aapka data sirf aapke liye hai. Hum kisi ke saath share nahi karte aur "
    "aapka data sirf aapke WhatsApp number se linked hai.\n\n"
    "Reply HAA to shuru karein."
)

ASK_AGAIN_MESSAGE = (
    "Shuru karne ke liye 'HAA' reply karein. Bina aapki ijazat ke hum koi "
    "data process nahi karte."
)

OPT_IN_KEYWORDS = {"haa", "haan", "yes", "ha"}


def get_or_create_user(phone_number: str) -> tuple[dict, bool]:
    """Returns (user_row, just_created) — creates an inactive row on first contact."""
    supabase = get_supabase()
    existing = (
        supabase.table("users").select("*").eq("phone_number", phone_number).execute()
    )
    if existing.data:
        return existing.data[0], False

    created = (
        supabase.table("users")
        .insert({"phone_number": phone_number, "is_active": False})
        .execute()
    )
    return created.data[0], True


def activate_user(phone_number: str) -> None:
    supabase = get_supabase()
    supabase.table("users").update({"is_active": True}).eq(
        "phone_number", phone_number
    ).execute()


def is_opt_in_reply(text: str) -> bool:
    return text.strip().lower() in OPT_IN_KEYWORDS
