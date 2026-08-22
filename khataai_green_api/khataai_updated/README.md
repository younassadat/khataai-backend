# KhataAI

AI bookkeeper for Pakistani social media sellers. Sellers forward WhatsApp receipts and voice notes → AI reads them → live ledger updated → monthly Urdu digest sent back automatically.

---

## What's built

| Phase | Feature | Status |
|---|---|---|
| 1 | FastAPI app + WhatsApp webhook | ✅ |
| 1 | Beta user whitelist | ✅ |
| 1 | API rate limiting (20 receipts/day) | ✅ |
| 2 | Receipt image OCR (Gemini 1.5 Flash) | ✅ |
| 2 | Permanent image storage (Supabase Storage) | ✅ |
| 2 | Debtor tracking via caption keyword | ✅ |
| 3 | Urdu chat interface + intent classifier | ✅ |
| 3 | Voice note support (audio → Gemini → intent) | ✅ |
| 4 | Monthly digest (pg_cron auto-send) | ✅ |
| 4 | Manual DIGEST trigger for testing | ✅ |
| 5 | Onboarding + privacy statement + HAA opt-in | ✅ |

---

## Project structure

```
khataai/
├── app/
│   ├── main.py                  # FastAPI app, webhook handler, routing
│   ├── gemini_client.py         # Gemini OCR + Urdu answer generation
│   ├── whatsapp.py              # Meta WhatsApp Cloud API calls
│   ├── supabase_client.py       # Supabase DB + Storage client
│   └── handlers/
│       ├── whitelist.py         # Beta user check (runs first)
│       ├── rate_limit.py        # Daily usage cap per user
│       ├── onboarding.py        # Welcome flow + HAA opt-in
│       ├── intent.py            # Message type classifier
│       ├── ledger.py            # DB writes + Urdu confirmations
│       ├── voice.py             # Voice note transcription + classification
│       └── digest.py            # Monthly digest sender
├── schema.sql                   # Full Supabase schema — run once in SQL editor
├── requirements.txt
└── .env.example
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in:

```
WHATSAPP_TOKEN=          # Meta permanent access token
WHATSAPP_PHONE_NUMBER_ID= # Your WhatsApp Business phone number ID
WHATSAPP_VERIFY_TOKEN=   # Your custom webhook verify token (any string)
GEMINI_API_KEY=          # Google AI Studio API key
SUPABASE_URL=            # Your Supabase project URL
SUPABASE_SERVICE_ROLE_KEY= # Supabase service role key (not anon key)
SUPABASE_STORAGE_BUCKET= # Default: receipts
CRON_SECRET=             # Secret header for the /internal/run-digest endpoint
DAILY_RECEIPT_LIMIT=     # Default: 20 — max receipts per user per day
```

---

## Setup

### 1. Supabase

Run `schema.sql` in your Supabase project → SQL Editor → New query.

This creates:
- `users` table (with rate limiting columns)
- `beta_users` table
- `ledger_entries` table
- `receipts` storage bucket
- Row Level Security policies
- `increment_daily_count` RPC function
- pg_cron jobs for monthly digest + daily limit reset

**Before running:** replace `+92XXXXXXXXXX` in the seed line with your own number.
**After deploying to Railway:** replace the placeholder URL and `CRON_SECRET` in the cron schedule.

### 2. Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Set all environment variables in Railway → Variables before deploying.

### 3. Meta WhatsApp Business API

1. Go to developers.facebook.com → Create App → Business
2. Add WhatsApp product
3. Get your Phone Number ID and permanent access token
4. Set webhook URL: `https://YOUR-RAILWAY-URL.up.railway.app/webhook`
5. Set verify token to match `WHATSAPP_VERIFY_TOKEN` in your .env
6. Subscribe to the `messages` webhook field

---

## Testing checklist

Run through these in order before giving the number to beta users:

- [ ] Unknown number messages → gets beta rejection message
- [ ] Your whitelisted number messages → gets welcome message
- [ ] Reply HAA → account activated
- [ ] Send a receipt photo → correct amount and vendor confirmed in Urdu
- [ ] Send receipt with caption "udhaar" → marked as unpaid, "(Udhaar mein add ho gaya)" in confirmation
- [ ] Type "is mahine kitna kamaya?" → correct earnings summary
- [ ] Type "kaun hisaab mein hai?" → debtor list or "sab clear hai"
- [ ] Send a voice note saying a payment amount → receipt logged correctly
- [ ] Type "digest" → monthly digest arrives
- [ ] Send 21 receipt photos → 21st gets the daily limit message
- [ ] Unknown number after limit reached → still gets rejection (not limit message)

---

## Key design decisions

**WhatsApp number = identity.** No signup, no passwords, no app download. Zero friction for the seller.

**Rate limiting applies only to AI-heavy operations.** Receipt scans and voice notes consume Gemini API credits. Text queries (earnings, debtors) are cheap and not rate-limited.

**Voice notes use a single Gemini call.** Transcription + intent classification happen in one API call — not two separate steps. This keeps latency low and cost minimal.

**Debtor tracking via caption keyword.** Seller types "udhaar" in the image caption to flag a receipt as unpaid. Simple, no NLP needed, seller controls it directly.

**Whitelist check is always first.** Before any DB lookup, AI call, or onboarding logic. An unknown number costs one Supabase read and nothing else.

**Rate limit check is second.** After whitelist, before any AI. Only applies to image and audio messages.
