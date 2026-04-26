-- Phase 1.x: fehlende plans-Tabelle fuer Plan-Persistenz nachziehen
-- Ziel: Backend save_plan/list_plans/get_plan laeuft stabil gegen Supabase.

create table if not exists public.plans (
  plan_id text primary key,
  title text not null,
  hypothesis text not null,
  literature_qc jsonb not null default '{}'::jsonb,
  protocol jsonb not null default '{}'::jsonb,
  materials jsonb not null default '[]'::jsonb,
  budget jsonb not null default '{}'::jsonb,
  timeline jsonb not null default '{}'::jsonb,
  validation jsonb not null default '{}'::jsonb,
  review_issues jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default timezone('utc', now()),
  knowledge_nodes_extracted jsonb not null default '[]'::jsonb
);

create index if not exists idx_plans_generated_at_desc
  on public.plans(generated_at desc);

-- Dev-first Rollout: Frontend darf lesen, writes ueber service_role.
alter table public.plans enable row level security;

drop policy if exists "plans_read_dev" on public.plans;
create policy "plans_read_dev"
on public.plans
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
      and tablename = 'plans'
  ) then
    execute 'alter publication supabase_realtime add table public.plans';
  end if;
end
$$;
