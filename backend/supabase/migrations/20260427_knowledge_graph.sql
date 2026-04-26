-- Phase 2 (Knowledge Graph): persistente Wissensknoten + Edges + Proposals
-- Ziel: Draft-Accept-Flow, Graph-Chat (RAG) und kontrollierte Save-Proposals.

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists vector;

-- 1) Knowledge Nodes: zentrale Wissenseinheiten (Experiment, Reagent, Claim, ...)
create table if not exists public.knowledge_nodes (
  id text primary key,
  title text not null,
  node_type text not null check (node_type in (
    'experiment', 'correction', 'reagent', 'claim', 'entity', 'literature', 'chat_insight'
  )),
  experiment_type text,
  content text,
  metadata jsonb not null default '{}'::jsonb,
  tags text[] not null default '{}',

  status text not null default 'pending'
    check (status in ('pending', 'active', 'archived')),
  source_type text not null default 'plan_draft'
    check (source_type in ('plan_draft', 'user_correction', 'chat_insight', 'literature', 'manual')),
  source_ref text,
  confidence numeric(4,3) not null default 0.7
    check (confidence >= 0 and confidence <= 1),
  times_applied integer not null default 1,

  embedding vector(1536),

  created_by text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_knowledge_nodes_status
  on public.knowledge_nodes(status);
create index if not exists idx_knowledge_nodes_type_status
  on public.knowledge_nodes(node_type, status);
create index if not exists idx_knowledge_nodes_source
  on public.knowledge_nodes(source_type, source_ref);
create index if not exists idx_knowledge_nodes_tags_gin
  on public.knowledge_nodes using gin(tags);
create index if not exists idx_knowledge_nodes_title_trgm
  on public.knowledge_nodes using gin (title gin_trgm_ops);
create index if not exists idx_knowledge_nodes_embedding_hnsw
  on public.knowledge_nodes
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- 2) Knowledge Edges: Beziehungen zwischen Knoten
create table if not exists public.knowledge_edges (
  id uuid primary key default gen_random_uuid(),
  source_id text not null references public.knowledge_nodes(id) on delete cascade,
  target_id text not null references public.knowledge_nodes(id) on delete cascade,
  relationship_type text not null,
  weight numeric(4,3) not null default 1.0,
  source_type text not null default 'plan_draft',
  source_ref text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  unique (source_id, target_id, relationship_type)
);

create index if not exists idx_knowledge_edges_source
  on public.knowledge_edges(source_id);
create index if not exists idx_knowledge_edges_target
  on public.knowledge_edges(target_id);
create index if not exists idx_knowledge_edges_relationship
  on public.knowledge_edges(relationship_type);

-- 3) Knowledge Proposals: vom User zu bestätigende Save-Vorschläge
create table if not exists public.knowledge_proposals (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('plan_draft', 'chat_insight')),
  source_ref text,
  payload jsonb not null,
  status text not null default 'pending'
    check (status in ('pending', 'confirmed', 'rejected')),
  created_by text,
  created_at timestamptz not null default timezone('utc', now()),
  decided_at timestamptz
);

create index if not exists idx_knowledge_proposals_status
  on public.knowledge_proposals(status);
create index if not exists idx_knowledge_proposals_kind
  on public.knowledge_proposals(kind);

-- 4) updated_at Trigger
create or replace function public.touch_knowledge_nodes_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists trg_knowledge_nodes_updated_at on public.knowledge_nodes;
create trigger trg_knowledge_nodes_updated_at
before update on public.knowledge_nodes
for each row execute function public.touch_knowledge_nodes_updated_at();

-- 5) RLS: Lesen frei (dev-first), Schreiben nur Service-Key
alter table public.knowledge_nodes enable row level security;
alter table public.knowledge_edges enable row level security;
alter table public.knowledge_proposals enable row level security;

drop policy if exists "knowledge_nodes_read_dev" on public.knowledge_nodes;
create policy "knowledge_nodes_read_dev"
on public.knowledge_nodes
for select
to anon, authenticated
using (true);

drop policy if exists "knowledge_edges_read_dev" on public.knowledge_edges;
create policy "knowledge_edges_read_dev"
on public.knowledge_edges
for select
to anon, authenticated
using (true);

drop policy if exists "knowledge_proposals_read_dev" on public.knowledge_proposals;
create policy "knowledge_proposals_read_dev"
on public.knowledge_proposals
for select
to anon, authenticated
using (true);

-- 6) Realtime-Publication für Knowledge-Garden Live-Updates
do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'knowledge_nodes'
  ) then
    execute 'alter publication supabase_realtime add table public.knowledge_nodes';
  end if;

  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'knowledge_edges'
  ) then
    execute 'alter publication supabase_realtime add table public.knowledge_edges';
  end if;

  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'knowledge_proposals'
  ) then
    execute 'alter publication supabase_realtime add table public.knowledge_proposals';
  end if;
end
$$;

-- 7) Helfer-RPC: hybride Suche (Embedding + Trigram + Tag-Boost)
create or replace function public.knowledge_search(
  query_embedding vector(1536),
  query_text text,
  experiment_type_filter text default null,
  match_count integer default 8
)
returns table (
  id text,
  title text,
  node_type text,
  experiment_type text,
  content text,
  tags text[],
  status text,
  confidence numeric,
  vector_score double precision,
  trigram_score double precision,
  combined_score double precision
)
language sql
stable
as $$
  select
    n.id,
    n.title,
    n.node_type,
    n.experiment_type,
    n.content,
    n.tags,
    n.status,
    n.confidence,
    case
      when n.embedding is null or query_embedding is null then 0.0
      else 1.0 - (n.embedding <=> query_embedding)
    end as vector_score,
    case
      when query_text is null or query_text = '' then 0.0
      else greatest(
        similarity(n.title, query_text),
        similarity(coalesce(n.content, ''), query_text)
      )
    end as trigram_score,
    (
      0.65 * case
        when n.embedding is null or query_embedding is null then 0.0
        else 1.0 - (n.embedding <=> query_embedding)
      end
      + 0.35 * case
        when query_text is null or query_text = '' then 0.0
        else greatest(
          similarity(n.title, query_text),
          similarity(coalesce(n.content, ''), query_text)
        )
      end
    ) as combined_score
  from public.knowledge_nodes n
  where n.status = 'active'
    and (experiment_type_filter is null or n.experiment_type = experiment_type_filter)
  order by combined_score desc
  limit greatest(match_count, 1);
$$;
