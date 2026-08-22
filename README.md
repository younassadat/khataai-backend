# KhataAI

AI bookkeeper for Pakistani social media sellers. Sellers forward WhatsApp receipts and voice notes — AI reads them, keeps a live ledger, and sends a monthly Urdu digest automatically.

## Tech stack
- FastAPI on Render
- Google Gemini 1.5 Flash (OCR + Urdu responses)
- Supabase (Postgres + Storage)
- WhatsApp Business Cloud API

## Features
- Receipt OCR from photos and screenshots
- Voice note support
- Urdu chat interface ("is mahine kitna kamaya?")
- Debtor tracking ("kaun hisaab mein hai?")
- Monthly auto-digest
- Beta user whitelist
- Daily rate limiting

## Setup

### 1. Supabase
Run `schema.sql` in Supabase SQL Editor. Enable `pg_cron` extension first under Database → Extensions.

### 2. Environment variables
Copy `.env.example` to `.env` and fill in all values.

### 3. Deploy to Render
- Connect your GitHub repo on render.com
- Set all env vars in Render dashboard
- Deploy

### 4. WhatsApp webhook
Set webhook URL to `https://YOUR-RENDER-URL/webhook` in Meta developer dashboard.

## Environment variables
See `.env.example` for all required variables.

## Built by
Team Chenab — Comebck Pakistan Cohort 1
