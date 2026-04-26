-- Phase 1 (P0): Schema-first Realtime Basis
-- Ziel: stabile run/event Persistenz, dev-first RLS und Realtime-Streaming.

create extension if not exists pgcrypto;

create table if not exists public.experiment_runs (
  run_id text primary key,
  hypothesis text not null,
  experiment_type text,
  status text not null check (status in ('pending', 'running', 'completed', 'failed')),
  plan_id text,
  error_message text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.agent_events (
  event_id uuid primary key default gen_random_uuid(),
  run_id text not null references public.experiment_runs(run_id) on delete cascade,
  sequence bigint not null,
  agent text not null,
  phase text not null check (phase in ('starting', 'progress', 'complete', 'error')),
  status text not null check (status in ('started', 'completed', 'failed')),
  message text,
  payload jsonb not null default '{}'::jsonb,
  from_agent text,
  to_agent text,
  "timestamp" timestamptz not null default timezone('utc', now())
);

create unique index if not exists idx_agent_events_run_sequence_unique
  on public.agent_events(run_id, sequence);

create index if not exists idx_agent_events_run_seq
  on public.agent_events(run_id, sequence);

create index if not exists idx_agent_events_timestamp
  on public.agent_events("timestamp");

-- updated_at bei Run-Patches immer aktuell halten.
create or replace function public.touch_experiment_runs_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists trg_experiment_runs_updated_at on public.experiment_runs;
create trigger trg_experiment_runs_updated_at
before update on public.experiment_runs
for each row execute function public.touch_experiment_runs_updated_at();

-- Dev-first Rollout: Frontend darf lesen, schreiben nur service_role (bypasst RLS).
alter table public.experiment_runs enable row level security;
alter table public.agent_events enable row level security;

drop policy if exists "experiment_runs_read_dev" on public.experiment_runs;
create policy "experiment_runs_read_dev"
on public.experiment_runs
for select
to anon, authenticated
using (true);

drop policy if exists "agent_events_read_dev" on public.agent_events;
create policy "agent_events_read_dev"
on public.agent_events
for select
to anon, authenticated
using (true);

-- Realtime für Event-Stream freischalten.
alter publication supabase_realtime add table public.agent_events;
