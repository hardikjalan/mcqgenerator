-- Cognira — Scope retrieval to the owner
-- Run this AFTER 07_chunks.sql and 08_ownership_hardening.sql.
-- Safe to run more than once.
--
-- Split out of 08 because it is the same class of fix applied to a different
-- table, and that table only exists once the RAG work is in. Keeping them
-- apart means 08 can be applied to any project, immediately, without also
-- taking the retrieval layer.

-- ═════════════════════════════════════════════════════════════════════════════
--  Retrieval chunks are scoped to their owner
-- ═════════════════════════════════════════════════════════════════════════════
-- match_chunks previously filtered on source_ids alone, and those come from
-- the client. With several faculty members sharing an index that is the same
-- class of bug as the storage policies: knowing an id is enough to read the
-- material. Owner is now a filter the caller cannot opt out of.
--
-- NULL p_owner_id still matches only rows with a NULL owner, so an
-- unauthenticated deployment sees only its own unowned rows rather than
-- everybody's.

DROP FUNCTION IF EXISTS public.match_chunks(extensions.vector, integer, double precision, uuid[]);

CREATE OR REPLACE FUNCTION public.match_chunks (
  query_embedding extensions.vector(768),
  match_count     integer default 8,
  min_score       double precision default 0.35,
  source_ids      uuid[] default null,
  p_owner_id      uuid default null
)
RETURNS TABLE (
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
LANGUAGE sql
STABLE
AS $$
  SELECT
    c.id,
    c.source_id,
    c.file_name,
    c.page_start,
    c.page_end,
    c.chunk_index,
    c.content,
    c.metadata,
    1 - (c.embedding <=> query_embedding) AS score
  FROM public.document_chunks c
  WHERE c.owner_id IS NOT DISTINCT FROM p_owner_id
    AND (source_ids IS NULL OR c.source_id = ANY (source_ids))
    AND 1 - (c.embedding <=> query_embedding) >= min_score
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
$$;
