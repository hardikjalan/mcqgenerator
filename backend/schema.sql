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
create index on document_chunks using hnsw (embedding vector_cosine_ops)
with (m = 16, ef_construction = 64);

-- Standard indexes for fast metadata filtering
create index idx_document_chunks_source_id on document_chunks(source_id);
create index idx_document_chunks_parent_id on document_chunks(parent_id);
