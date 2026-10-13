-- Gateway schema v1. Postgres 15+. All times timestamptz (UTC). Money = integer micros (1e-6 USD).
-- Access: every query is scoped by org_id in the data layer (FastAPI dependency injects org from verified session/key);
-- RLS is enabled as defence in depth using `set local app.org_id = ...` per transaction.
create extension if not exists pgcrypto;

create table organizations (
  id uuid primary key default gen_random_uuid(),
  external_org_id text unique,            -- NEXORA account/Clerk org id
  name text not null,
  plan text not null default 'free' check (plan in ('free','starter','team','enterprise')),
  monthly_call_quota integer not null default 100,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table members (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  external_user_id text not null,
  email text not null,
  role text not null default 'developer' check (role in ('owner','admin','developer','viewer')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, external_user_id)
);
create index on members (external_user_id);

create table api_keys (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  prefix text not null,                    -- e.g. nx_live_ab12 (shown)
  key_hash bytea not null unique,          -- sha256 of full secret; secret shown once
  last4 text not null,
  rpm_limit integer not null default 60 check (rpm_limit > 0),
  last_used_at timestamptz,
  revoked_at timestamptz,
  created_by uuid references members(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on api_keys (org_id, revoked_at);

create table provider_connections (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  provider text not null check (provider in ('anthropic','openai','azure_openai')),
  label text not null,
  credential_enc bytea not null,           -- AES-GCM, key from KMS/env, never returned by API
  base_url text,
  is_default boolean not null default false,
  status text not null default 'untested' check (status in ('untested','ok','failing')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on provider_connections (org_id);
create unique index one_default_provider on provider_connections (org_id) where is_default;

create table policies (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  type text not null check (type in ('model_allow','dlp','injection','rate')),
  config jsonb not null default '{}',
  mode text not null default 'monitor' check (mode in ('off','monitor','enforce')),
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, type)
);

create table request_logs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  key_id uuid references api_keys(id) on delete set null,
  request_id text not null,
  ts timestamptz not null default now(),
  provider text, model text,
  status_code integer not null,
  decision text not null check (decision in ('allow','flag','block','error')),
  risk_score smallint check (risk_score between 0 and 100),
  prompt_hash bytea,                       -- sha256; raw prompt NOT stored by default
  tokens_in integer not null default 0,
  tokens_out integer not null default 0,
  cost_micros bigint not null default 0,
  latency_ms integer,
  created_at timestamptz not null default now()
);
create index on request_logs (org_id, ts desc);
create index on request_logs (org_id, key_id, ts desc);
create index on request_logs (org_id, decision, ts desc);
-- partition by month once > ~50M rows

create table security_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  log_id uuid not null references request_logs(id) on delete cascade,
  type text not null check (type in ('prompt_injection','dlp_pii','dlp_secret','dlp_financial','policy_denied','rate_limited')),
  severity text not null check (severity in ('low','medium','high','critical')),
  rule_id text,
  redacted_excerpt text,
  ts timestamptz not null default now()
);
create index on security_events (org_id, ts desc);
create index on security_events (log_id);

create table usage_daily (
  org_id uuid not null references organizations(id) on delete cascade,
  key_id uuid references api_keys(id) on delete cascade,
  day date not null,
  calls integer not null default 0,
  blocked integer not null default 0,
  tokens_in bigint not null default 0,
  tokens_out bigint not null default 0,
  cost_micros bigint not null default 0,
  primary key (org_id, day, key_id)
);

create table subscriptions (
  org_id uuid primary key references organizations(id) on delete cascade,
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  plan text not null,
  status text not null check (status in ('active','past_due','canceled','trialing','incomplete')),
  current_period_end timestamptz,
  updated_at timestamptz not null default now()
);

create table stripe_events (            -- idempotency for webhooks
  id text primary key,
  received_at timestamptz not null default now()
);

create table webhooks (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  url text not null,
  secret_enc bytea not null,
  events text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on webhooks (org_id);

-- RLS defence in depth
do $$ declare t text; begin
  foreach t in array array['members','api_keys','provider_connections','policies','request_logs','security_events','usage_daily','webhooks'] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy org_isolation on %I using (org_id = nullif(current_setting(''app.org_id'', true), '''')::uuid)', t);
  end loop;
end $$;
