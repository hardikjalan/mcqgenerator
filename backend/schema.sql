-- ────────────────────────────────────────────────────────────────────────────
-- schema.sql
-- Manual SQL migration for Layer 4: Embedding & Supabase Vector Storage
-- Run this script in your Supabase SQL Editor.
-- ────────────────────────────────────────────────────────────────────────────

-- Enable pgvector if not already enabled
create extension if not exists vector;

-- Create the document chunks table
create table if not exists document_chunks (
    -- Internal DB ID
    id uuid primary key default gen_random_uuid(),
    
    -- Node provenance
    node_id text unique not null,
    parent_id text,
    source_id text not null,
    
    -- Content and embeddings
    content text not null,
    embedding vector(1536), -- text-embedding-3-small dimension
    
    -- Preserved Layer 3 metadata (hierarchy, semantic type, pages)
    metadata jsonb default '{}'::jsonb,
    
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Create HNSW index for cosine similarity
create index if not exists idx_document_chunks_embedding on document_chunks using hnsw (embedding vector_cosine_ops)
with (m = 16, ef_construction = 64);

-- Standard indexes for fast metadata filtering
create index if not exists idx_document_chunks_source_id on document_chunks(source_id);
create index if not exists idx_document_chunks_parent_id on document_chunks(parent_id);

-- ────────────────────────────────────────────────────────────────────────────
-- Layer 5: Vector Similarity Search RPC
-- ────────────────────────────────────────────────────────────────────────────

create or replace function match_document_chunks (
  query_embedding vector(1536),
  match_count int default 5,
  filter_source_ids text[] default '{}'
) returns table (
  id uuid,
  node_id text,
  parent_id text,
  source_id text,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    dc.id,
    dc.node_id,
    dc.parent_id,
    dc.source_id,
    dc.content,
    dc.metadata,
    (1 - (dc.embedding <=> query_embedding))::float as similarity
  from document_chunks dc
  -- Only match against child chunks (which have non-null embeddings)
  where dc.embedding is not null
    -- Enforce document isolation when filter_source_ids is supplied
    and (filter_source_ids is null or cardinality(filter_source_ids) = 0 or dc.source_id = any(filter_source_ids))
  order by dc.embedding <=> query_embedding
  limit match_count;
end;
$$;

