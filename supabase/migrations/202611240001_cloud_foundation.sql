begin;

create extension if not exists pgcrypto;

create type public.alert_state as enum ('WATCH', 'READY');
create type public.position_status as enum ('OPEN', 'CLOSED', 'CANCELLED');
create type public.evidence_kind as enum ('BACKTEST', 'REPLAY', 'LIVE_PAPER');
create type public.outbox_status as enum ('PENDING', 'SENDING', 'SENT', 'FAILED');

create table public.instruments (
  id uuid primary key default gen_random_uuid(), symbol text not null, exchange text not null default 'NSE',
  series text not null default 'EQ', company_name text, sector text, active boolean not null default true,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique (exchange, symbol, series)
);
create table public.market_candles (
  id uuid primary key default gen_random_uuid(), instrument_id uuid not null references public.instruments(id),
  timeframe text not null, observed_at timestamptz not null, open numeric not null, high numeric not null,
  low numeric not null, close numeric not null, volume numeric not null default 0, source text not null,
  observation_kind text not null check (observation_kind in ('LIVE','RECOVERY')), ingested_at timestamptz not null default now(),
  unique (instrument_id, timeframe, observed_at, source)
);
create table public.scan_runs (
  id uuid primary key default gen_random_uuid(), owner_id uuid references auth.users(id), job_key text not null,
  strategy_version text not null, status text not null, started_at timestamptz not null default now(),
  completed_at timestamptz, universe_size integer not null default 0, evaluated_count integer not null default 0,
  ready_count integer not null default 0, watch_count integer not null default 0, error text, metadata jsonb not null default '{}'::jsonb,
  unique (job_key, strategy_version)
);
create table public.trade_alerts (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  scan_run_id uuid references public.scan_runs(id), instrument_id uuid not null references public.instruments(id),
  state public.alert_state not null, score numeric not null, probability numeric,
  entry_price numeric not null, stop_loss numeric not null, tp1 numeric not null, tp2 numeric not null,
  rationale jsonb not null default '[]'::jsonb, status text not null default 'ACTIVE', strategy_version text not null,
  created_at timestamptz not null default now(), expires_at timestamptz,
  unique (owner_id, scan_run_id, instrument_id)
);
create table public.paper_positions (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  alert_id uuid references public.trade_alerts(id), instrument_id uuid not null references public.instruments(id),
  evidence public.evidence_kind not null default 'LIVE_PAPER', status public.position_status not null default 'OPEN',
  quantity numeric not null check (quantity > 0), entry_price numeric not null, stop_loss numeric not null,
  tp1 numeric not null, tp2 numeric not null, opened_at timestamptz not null default now(), closed_at timestamptz,
  realized_pnl numeric not null default 0, entry_idempotency_key text not null unique,
  metadata jsonb not null default '{}'::jsonb
);
create table public.paper_execution_events (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  position_id uuid not null references public.paper_positions(id), candle_id uuid references public.market_candles(id),
  event_type text not null, event_at timestamptz not null, price numeric, quantity numeric,
  ambiguous boolean not null default false, idempotency_key text not null unique, details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create table public.user_positions (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  instrument_id uuid not null references public.instruments(id), quantity numeric not null, average_price numeric not null,
  status text not null default 'OPEN', opened_at timestamptz not null default now(), closed_at timestamptz,
  created_at timestamptz not null default now()
);
create table public.user_transactions (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  position_id uuid references public.user_positions(id), instrument_id uuid not null references public.instruments(id),
  side text not null check (side in ('BUY','SELL')), quantity numeric not null check (quantity > 0),
  price numeric not null, fees numeric not null default 0, transacted_at timestamptz not null,
  idempotency_key text not null unique, notes text, created_at timestamptz not null default now()
);
create table public.position_reviews (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  position_id uuid not null references public.user_positions(id), verdict text not null, score numeric,
  reasons jsonb not null default '[]'::jsonb, reviewed_at timestamptz not null default now(),
  unique (position_id, reviewed_at)
);
create table public.portfolio_snapshots (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  snapshot_date date not null, invested_value numeric not null default 0, market_value numeric not null default 0,
  cash_value numeric not null default 0, realized_pnl numeric not null default 0, unrealized_pnl numeric not null default 0,
  drawdown_pct numeric not null default 0, details jsonb not null default '{}'::jsonb,
  unique (owner_id, snapshot_date)
);
create table public.strategy_performance (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  strategy_version text not null, evidence public.evidence_kind not null, as_of_date date not null,
  trades integer not null default 0, win_rate numeric, expectancy numeric, max_drawdown_pct numeric,
  return_pct numeric, metrics jsonb not null default '{}'::jsonb,
  unique (owner_id, strategy_version, evidence, as_of_date)
);
create table public.scan_checkpoints (
  id uuid primary key default gen_random_uuid(), scan_run_id uuid not null references public.scan_runs(id) on delete cascade,
  cursor_value text, processed_count integer not null default 0, state jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(), unique (scan_run_id)
);
create table public.scheduled_jobs (
  id uuid primary key default gen_random_uuid(), job_key text not null unique, schedule text not null, enabled boolean not null default true,
  lease_owner text, lease_expires_at timestamptz, last_started_at timestamptz, last_completed_at timestamptz,
  last_status text, last_error text, updated_at timestamptz not null default now()
);
create table public.market_data_checkpoints (
  id uuid primary key default gen_random_uuid(), provider text not null, instrument_id uuid references public.instruments(id),
  timeframe text not null, last_observed_at timestamptz, cursor_value text, updated_at timestamptz not null default now(),
  unique (provider, instrument_id, timeframe)
);
create table public.telegram_users (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  chat_id bigint not null unique, username text, authorized boolean not null default false,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(owner_id)
);
create table public.notification_outbox (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  channel text not null, recipient text not null, template text not null, payload jsonb not null,
  status public.outbox_status not null default 'PENDING', attempts integer not null default 0,
  available_at timestamptz not null default now(), sent_at timestamptz, last_error text,
  dedupe_key text not null unique, created_at timestamptz not null default now()
);
create table public.notification_history (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  outbox_id uuid references public.notification_outbox(id), channel text not null, provider_message_id text,
  status text not null, response jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create table public.risk_settings (
  owner_id uuid primary key references auth.users(id), capital numeric not null default 50000,
  risk_per_trade_pct numeric not null default 1 check (risk_per_trade_pct > 0 and risk_per_trade_pct <= 2),
  max_open_positions integer not null default 5, max_portfolio_risk_pct numeric not null default 5,
  live_orders_enabled boolean not null default false, updated_at timestamptz not null default now()
);
create table public.system_health (
  component text primary key, status text not null, checked_at timestamptz not null default now(),
  latency_ms integer, details jsonb not null default '{}'::jsonb
);

create index market_candles_lookup on public.market_candles(instrument_id, timeframe, observed_at desc);
create index alerts_owner_created on public.trade_alerts(owner_id, created_at desc);
create index positions_owner_status on public.paper_positions(owner_id, status);
create unique index one_open_user_position_per_instrument on public.user_positions(owner_id, instrument_id) where status='OPEN';
create index outbox_delivery on public.notification_outbox(status, available_at) where status in ('PENDING','FAILED');

alter table public.instruments enable row level security;
alter table public.market_candles enable row level security;
alter table public.scan_runs enable row level security;
alter table public.trade_alerts enable row level security;
alter table public.paper_positions enable row level security;
alter table public.paper_execution_events enable row level security;
alter table public.user_positions enable row level security;
alter table public.user_transactions enable row level security;
alter table public.position_reviews enable row level security;
alter table public.portfolio_snapshots enable row level security;
alter table public.strategy_performance enable row level security;
alter table public.scan_checkpoints enable row level security;
alter table public.scheduled_jobs enable row level security;
alter table public.market_data_checkpoints enable row level security;
alter table public.telegram_users enable row level security;
alter table public.notification_outbox enable row level security;
alter table public.notification_history enable row level security;
alter table public.risk_settings enable row level security;
alter table public.system_health enable row level security;

create policy "authenticated instruments read" on public.instruments for select to authenticated using (true);
create policy "authenticated candles read" on public.market_candles for select to authenticated using (true);
create policy "own scan runs read" on public.scan_runs for select to authenticated using (owner_id = auth.uid());
create policy "own alerts" on public.trade_alerts for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own paper positions" on public.paper_positions for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own execution events" on public.paper_execution_events for select to authenticated using (owner_id = auth.uid());
create policy "own user positions" on public.user_positions for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own transactions" on public.user_transactions for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own reviews" on public.position_reviews for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own snapshots" on public.portfolio_snapshots for select to authenticated using (owner_id = auth.uid());
create policy "own performance" on public.strategy_performance for select to authenticated using (owner_id = auth.uid());
create policy "own telegram" on public.telegram_users for select to authenticated using (owner_id = auth.uid());
create policy "own notification outbox" on public.notification_outbox for select to authenticated using (owner_id = auth.uid());
create policy "own notification history" on public.notification_history for select to authenticated using (owner_id = auth.uid());
create policy "own risk settings" on public.risk_settings for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "health read" on public.system_health for select to authenticated using (true);

create or replace function public.claim_scheduled_job(p_job_key text, p_worker text, p_lease_seconds integer default 120)
returns public.scheduled_jobs language plpgsql security definer set search_path = public as $$
declare claimed public.scheduled_jobs;
begin
  update public.scheduled_jobs set lease_owner=p_worker,
    lease_expires_at=now()+make_interval(secs => p_lease_seconds), last_started_at=now(), last_status='RUNNING', updated_at=now()
  where job_key=p_job_key and enabled and (lease_expires_at is null or lease_expires_at < now()) returning * into claimed;
  return claimed;
end $$;
revoke all on function public.claim_scheduled_job(text,text,integer) from public, anon, authenticated;
grant execute on function public.claim_scheduled_job(text,text,integer) to service_role;

commit;
