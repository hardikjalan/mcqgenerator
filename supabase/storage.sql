-- Cognira Storage: faculty-documents Bucket Policies
-- Run this in your Supabase SQL Editor AFTER creating the bucket.

-- ── Step 1: Ensure the bucket exists ─────────────────────────────────────────
INSERT INTO storage.buckets (id, name, public)
VALUES ('faculty-documents', 'faculty-documents', false)
ON CONFLICT (id) DO NOTHING;

-- ── Step 2: Drop old policies to avoid conflicts ──────────────────────────────
DROP POLICY IF EXISTS "Allow faculty to upload files"  ON storage.objects;
DROP POLICY IF EXISTS "Allow faculty to view files"    ON storage.objects;
DROP POLICY IF EXISTS "Allow faculty to delete files"  ON storage.objects;

-- ── Step 3: INSERT — only faculty can upload ──────────────────────────────────
CREATE POLICY "Allow faculty to upload files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'faculty-documents'
  AND (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE profiles.id = auth.uid()
        AND profiles.role = 'faculty'::user_role
    )
  )
);

-- ── Step 4: SELECT — only faculty can read their own files ────────────────────
CREATE POLICY "Allow faculty to view files"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'faculty-documents'
  AND (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE profiles.id = auth.uid()
        AND profiles.role = 'faculty'::user_role
    )
  )
);

-- ── Step 5: DELETE — faculty can remove their own files ───────────────────────
CREATE POLICY "Allow faculty to delete files"
ON storage.objects FOR DELETE
TO authenticated
USING (
  bucket_id = 'faculty-documents'
  AND (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE profiles.id = auth.uid()
        AND profiles.role = 'faculty'::user_role
    )
  )
);
