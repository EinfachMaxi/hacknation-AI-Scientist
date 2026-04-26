-- Phase 1 (Dynamic Orchestration): Agent Registry + Run Lifecycle + Messaging
-- Ziel: dynamische Agentenauswahl aus DB und persistente Inter-Agent-Kommunikation.

create extension if not exists pgcrypto;

create table if not exists public.agents (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  name text not null,
  role text not null,
  personality text,
  capabilities text[] not null default '{}',
  prompt_template text not null,
  is_active boolean not null default true,
  sort_order int not null default 100,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_agents_is_active on public.agents(is_active);
create index if not exists idx_agents_capabilities_gin on public.agents using gin(capabilities);

create table if not exists public.run_agents (
  id uuid primary key default gen_random_uuid(),
  run_id text not null references public.experiment_runs(run_id) on delete cascade,
  agent_id uuid not null references public.agents(id) on delete restrict,
  status text not null check (status in ('pending', 'ready', 'running', 'completed', 'failed', 'skipped')),
  progress_pct int not null default 0 check (progress_pct >= 0 and progress_pct <= 100),
  started_at timestamptz,
  completed_at timestamptz,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (run_id, agent_id)
);

create index if not exists idx_run_agents_run_id on public.run_agents(run_id);
create index if not exists idx_run_agents_status on public.run_agents(status);
create index if not exists idx_run_agents_run_status on public.run_agents(run_id, status);

create table if not exists public.agent_messages (
  id uuid primary key default gen_random_uuid(),
  run_id text not null references public.experiment_runs(run_id) on delete cascade,
  sequence bigint not null,
  message_type text not null check (message_type in ('request', 'response', 'handoff', 'broadcast', 'system')),
  from_agent_id uuid references public.agents(id) on delete set null,
  to_agent_id uuid references public.agents(id) on delete set null,
  from_agent text,
  to_agent text,
  subject text,
  message text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  unique (run_id, sequence)
);

create index if not exists idx_agent_messages_run_created_at on public.agent_messages(run_id, created_at);
create index if not exists idx_agent_messages_message_type on public.agent_messages(message_type);
create index if not exists idx_agent_messages_from_agent_id on public.agent_messages(from_agent_id);
create index if not exists idx_agent_messages_to_agent_id on public.agent_messages(to_agent_id);

alter table public.agent_events
  add column if not exists agent_id uuid references public.agents(id) on delete set null;

create index if not exists idx_agent_events_agent_id on public.agent_events(agent_id);

create or replace function public.touch_agents_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create or replace function public.touch_run_agents_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists trg_agents_updated_at on public.agents;
create trigger trg_agents_updated_at
before update on public.agents
for each row execute function public.touch_agents_updated_at();

drop trigger if exists trg_run_agents_updated_at on public.run_agents;
create trigger trg_run_agents_updated_at
before update on public.run_agents
for each row execute function public.touch_run_agents_updated_at();

-- Dev-first Rollout: Frontend darf lesen, schreiben nur service_role.
alter table public.agents enable row level security;
alter table public.run_agents enable row level security;
alter table public.agent_messages enable row level security;

drop policy if exists "agents_read_dev" on public.agents;
create policy "agents_read_dev"
on public.agents
for select
to anon, authenticated
using (true);

drop policy if exists "run_agents_read_dev" on public.run_agents;
create policy "run_agents_read_dev"
on public.run_agents
for select
to anon, authenticated
using (true);

drop policy if exists "agent_messages_read_dev" on public.agent_messages;
create policy "agent_messages_read_dev"
on public.agent_messages
for select
to anon, authenticated
using (true);

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'run_agents'
  ) then
    execute 'alter publication supabase_realtime add table public.run_agents';
  end if;

  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'agent_messages'
  ) then
    execute 'alter publication supabase_realtime add table public.agent_messages';
  end if;
end
$$;
