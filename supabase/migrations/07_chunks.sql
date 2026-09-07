-- 07_chunks.sql
-- =============
-- Vector storage for RAG retrieval.
--
-- Chunks of uploaded course material, each with the embedding used to find it.
-- Idempotent, like the other migrations — safe to re-run.

-- pgvector ships with Supabase but is not enabled by default.
create extension if not exists vector with schema extensions;


-- ── Table ────────────────────────────────────────────────────────────────────
-- The id is "<source_id>:<n>", generated deterministically by the chunker
-- rather than by the database. That is what makes re-uploading a file replace
-- its chunks instead of silently storing a second copy of the document.
--
-- The vector width must match EMBED_DIMENSIONS in backend/app/config.py.
-- Postgres bakes it into the column, so changing one without the other fails
-- every insert — and changing it at all means re-embedding everything, since
-- vectors of different widths (or from different models) are not comparable.

create table if not exists public.document_chunks (
  id            text primary key,
  source_id     uuid not null,
  owner_id      uuid references auth.users (id) on delete cascade,
  file_name     text not null,
  page_start    integer,
  page_end      integer,
  chunk_index   integer not null,
  content       text not null,
  metadata      jsonb not null default '{}'::jsonb,
  embedding     extensions.vector(768) not null,
  created_at    timestamptz not null default now()
);

-- Deleting and re-indexing one upload is by source, so this is the hot path.
create index if not exists document_chunks_source_id_idx
  on public.document_chunks (source_id);

create index if not exists document_chunks_owner_id_idx
  on public.document_chunks (owner_id);

-- HNSW rather than IVFFlat: it needs no training pass over existing rows, so
-- it works on an empty table and stays accurate as rows are added — which
-- suits a corpus that grows one upload at a time. vector_cosine_ops must match
-- the operator used in match_chunks below (<=>), or the index is ignored and
-- every query becomes a full scan.
create index if not exists document_chunks_embedding_idx
  on public.document_chunks
  using hnsw (embedding extensions.vector_cosine_ops);


-- ── Row-level security ───────────────────────────────────────────────────────
-- The backend writes with the service-role key, which bypasses RLS. These
-- policies exist for anything reaching the table with a user's own token.

alter table public.document_chunks enable row level security;

drop policy if exists "own chunks are readable" on public.document_chunks;
create policy "own chunks are readable"
  on public.document_chunks for select
  using (auth.uid() = owner_id);

drop policy if exists "own chunks are writable" on public.document_chunks;
create policy "own chunks are writable"
  on public.document_chunks for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);


-- ── Similarity search ────────────────────────────────────────────────────────
-- Exposed as an RPC because PostgREST cannot express a vector distance
-- ordering through its query syntax.
--
-- pgvector's <=> is cosine *distance*, so 0 means identical. Similarity is
-- 1 - distance, which is what callers think in and what min_score compares.
--
-- source_ids scopes a search to the files in the request being served. Without
-- it a search would range over every document ever uploaded by anyone.

create or replace function public.match_chunks (
  query_embedding extensions.vector(768),
  match_count     integer default 8,
  min_score       double precision default 0.35,
  source_ids      uuid[] default null
)
returns table (
  id          text,
  source_id   uuid,
  file_name   text,
  page_start  integer,
  page_end    integer,
  chunk_index integer,
  content     text,
  metadata    jsonb,
  score       double precision
)
language sql
stable
as $$
  select
    c.id,
    c.source_id,
    c.file_name,
    c.page_start,
    c.page_end,
    c.chunk_index,
    c.content,
    c.metadata,
    1 - (c.embedding <=> query_embedding) as score
  from public.document_chunks c
  where (source_ids is null or c.source_id = any (source_ids))
    and 1 - (c.embedding <=> query_embedding) >= min_score
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
