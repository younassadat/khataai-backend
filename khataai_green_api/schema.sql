-- KhataAI database schema
-- Run this in Supabase's SQL editor (Project -> SQL Editor -> New query)

-- ============================================================
-- Table: users
-- ============================================================
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  phone_number text unique not null,
  name text,
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);

-- ============================================================
-- Table: beta_users
-- ============================================================
create table if not exists beta_users (
  id uuid primary key default gen_random_uuid(),
  phone_number text unique not null,
  name text,
  added_by text,
  added_at timestamptz not null default now()
);

-- ============================================================
-- Table: ledger_entries
-- ============================================================
create table if not exists ledger_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  date date not null,
  amount decimal not null,
  vendor text,
  type text not null check (type in ('income', 'expense')),
  image_url text,
  raw_text text,
  is_paid boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists idx_ledger_user_date on ledger_entries(user_id, date);

-- ============================================================
-- Storage: private bucket for permanent receipt images.
-- The backend uploads here and generates a signed URL — Meta's own CDN
-- URLs for media expire, so this is where receipt images actually live
-- long-term.
-- ============================================================
insert into storage.buckets (id, name, public)
values ('receipts', 'receipts', false)
on conflict (id) do nothing;

-- ============================================================
-- Row Level Security
-- The backend uses the Supabase SERVICE ROLE key (bypasses RLS by design),
-- so these policies protect against any future client-side / anon-key access.
-- ============================================================
alter table users enable row level security;
alter table ledger_entries enable row level security;
alter table beta_users enable row level security;

-- No public policies are created: only the service role (used by the
-- FastAPI backend) can read/write. This is intentional for an MVP where
-- WhatsApp number = identity and there is no end-user-facing client.

-- ============================================================
-- Seed yourself as a beta user so you can test immediately
-- ============================================================
insert into beta_users (phone_number, name, added_by)
values ('+92XXXXXXXXXX', 'Your Name', 'yahya')
on conflict (phone_number) do nothing;

-- ============================================================
-- Phase 4: monthly digest cron
-- pg_cron can't call an external HTTPS endpoint on its own — it needs the
-- pg_net extension to make the HTTP call. Enable both, then schedule:
-- ============================================================
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule(
  'khataai-monthly-digest',
  '0 9 1 * *',
  $$
  select net.http_post(
    url := 'https://YOUR-RAILWAY-APP.up.railway.app/internal/run-digest',
    headers := jsonb_build_object('x-cron-secret', 'REPLACE_WITH_YOUR_CRON_SECRET'),
    body := '{}'::jsonb
  );
  $$
);

-- To test without waiting: message the bot with the word "digest"
-- (handled in app/handlers/intent.py) instead of waiting for the cron.

-- ============================================================
-- Phase 1 update: API rate limiting
-- Adds daily_message_count + last_reset_date to users.
-- ============================================================
alter table users
  add column if not exists daily_message_count integer not null default 0,
  add column if not exists last_reset_date date not null default current_date;

-- Atomic increment function — avoids race conditions when two messages
-- arrive from the same user at the same time.
create or replace function increment_daily_count(target_user_id uuid)
returns void
language plpgsql
as $$
begin
  update users
  set daily_message_count = daily_message_count + 1
  where id = target_user_id;
end;
$$;

-- Daily reset cron — runs at midnight UTC (5am PKT) every day.
-- Resets all counters so the new day starts fresh.
select cron.schedule(
  'khataai-daily-limit-reset',
  '0 0 * * *',
  $$
  update users
  set daily_message_count = 0,
      last_reset_date = current_date;
  $$
);
