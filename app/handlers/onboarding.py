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

ASK_BUSINESS_NAME = "Aapki dukaan ya business ka naam kya hai?"

ASK_BUSINESS_TYPE = (
    "Aapka business kis type ka hai? (e.g. Kirana Store, Tailor, Mobile Shop, Salon)"
)

ONBOARDING_COMPLETE_MESSAGE = "Shukriya! Ab aap receipts bhej sakte hain."

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
        .insert({"phone_number": phone_number, "is_active": False, "onboarding_step": "awaiting_optin"})
        .execute()
    )
    return created.data[0], True


def advance_to_business_name(phone_number: str) -> None:
    supabase = get_supabase()
    supabase.table("users").update(
        {"onboarding_step": "awaiting_business_name"}
    ).eq("phone_number", phone_number).execute()


def save_business_name(phone_number: str, name: str) -> None:
    supabase = get_supabase()
    supabase.table("users").update(
        {"business_name": name.strip(), "onboarding_step": "awaiting_business_type"}
    ).eq("phone_number", phone_number).execute()


def save_business_type(phone_number: str, biz_type: str) -> None:
    supabase = get_supabase()
    supabase.table("users").update(
        {"business_type": biz_type.strip(), "onboarding_step": "done", "is_active": True}
    ).eq("phone_number", phone_number).execute()


def activate_user(phone_number: str) -> None:
    """Kept for backward compatibility — direct activation with no business info."""
    supabase = get_supabase()
    supabase.table("users").update({"is_active": True}).eq(
        "phone_number", phone_number
    ).execute()


def is_opt_in_reply(text: str) -> bool:
    return text.strip().lower() in OPT_IN_KEYWORDS
