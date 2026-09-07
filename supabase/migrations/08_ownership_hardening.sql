-- Cognira — Ownership hardening
-- Run this AFTER 07_chunks.sql in your Supabase SQL Editor.
-- Safe to run more than once.
--
-- Fixes two holes that only appear once a second faculty member signs up. Both
-- were correct in intent and unenforced in the database, which is the only
-- place enforcement counts — a policy the frontend keeps is a convention, not
-- a control.
--
-- This file depends on nothing but 01-06, so it can be applied on its own —
-- including on a project that has none of the RAG work. The equivalent fix for
-- the retrieval tables lives in 09, which needs 07.
--
-- This is a new migration rather than an edit to 04 and 05, because those have
-- already run on any live project: re-editing them changes what a fresh setup
-- does while leaving an existing database untouched, which is the worst of
-- both. Running 01 → 08 in order gives a correct database either way.


-- ═════════════════════════════════════════════════════════════════════════════
--  1. Storage: a faculty member may only touch their own files
-- ═════════════════════════════════════════════════════════════════════════════
-- The old policies asked "is the caller faculty?" and stopped there. Every
-- faculty member could therefore read and delete every other faculty member's
-- uploads — including through a signed URL, which is how this backend reads
-- files, so it was reachable from the API too.
--
-- Uploads already go to '{userId}/{timestamp}_{random}.{ext}' (see
-- frontend/components/faculty/FileUploadZone.tsx), so ownership is recoverable
-- from the path: storage.foldername(name) splits on '/', and element 1 is that
-- leading user id.
--
-- INSERT is fixed too, though it was not part of the original report. Without
-- it a faculty member can write *into another user's folder*, and a file
-- planted there is owned by that user under the check below — the path is the
-- identity, so it has to be constrained on the way in as well as on the way
-- out.

DROP POLICY IF EXISTS "Allow faculty to upload files" ON storage.objects;
DROP POLICY IF EXISTS "Allow faculty to view files"   ON storage.objects;
DROP POLICY IF EXISTS "Allow faculty to delete files" ON storage.objects;

CREATE POLICY "Allow faculty to upload files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'faculty-documents'
  AND (storage.foldername(name))[1] = auth.uid()::text
  AND EXISTS (
    SELECT 1 FROM public.profiles
    WHERE profiles.id = auth.uid()
      AND profiles.role = 'faculty'::user_role
  )
);

CREATE POLICY "Allow faculty to view files"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'faculty-documents'
  AND (storage.foldername(name))[1] = auth.uid()::text
  AND EXISTS (
    SELECT 1 FROM public.profiles
    WHERE profiles.id = auth.uid()
      AND profiles.role = 'faculty'::user_role
  )
);

CREATE POLICY "Allow faculty to delete files"
ON storage.objects FOR DELETE
TO authenticated
USING (
  bucket_id = 'faculty-documents'
  AND (storage.foldername(name))[1] = auth.uid()::text
  AND EXISTS (
    SELECT 1 FROM public.profiles
    WHERE profiles.id = auth.uid()
      AND profiles.role = 'faculty'::user_role
  )
);


-- ═════════════════════════════════════════════════════════════════════════════
--  2. The admin role cannot be self-assigned
-- ═════════════════════════════════════════════════════════════════════════════
-- set_profile_role takes p_role of type user_role, and that enum includes
-- 'admin'. The onboarding screen only offers student and faculty, but the
-- screen is not what enforces it — anyone with the anon key could call
--
--   supabase.rpc('set_profile_role', { p_role: 'admin', ... })
--
-- on a fresh account, where role is still NULL, and become an admin. The
-- REVOKE UPDATE (role) in 03_policies.sql does not help: this function is
-- SECURITY DEFINER and runs as the database owner precisely so it can bypass
-- that.
--
-- The guard is a whitelist rather than a check for 'admin'. Blacklisting the
-- one role we can think of today means the next privileged role added to the
-- enum is self-assignable until somebody remembers this function exists.
--
-- Admins are granted deliberately, by an existing admin or by hand in the SQL
-- editor — never through onboarding.

CREATE OR REPLACE FUNCTION public.set_profile_role(
  p_role        user_role,
  p_full_name   TEXT,
  p_institution TEXT
)
RETURNS user_role AS $$
DECLARE
  v_uid  UUID := auth.uid();
  v_role user_role;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not signed in';
  END IF;

  -- Only self-selectable roles may come through onboarding.
  IF p_role IS NULL OR p_role NOT IN ('student'::user_role, 'faculty'::user_role) THEN
    RAISE EXCEPTION 'Role % cannot be self-assigned', COALESCE(p_role::TEXT, 'null')
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- Email and avatar come from auth.users rather than the caller, so the row
  -- can satisfy profiles.email NOT NULL without trusting client input.
  INSERT INTO public.profiles (id, email, full_name, avatar_url, role, institution)
  SELECT
    u.id,
    u.email,
    COALESCE(NULLIF(p_full_name, ''), u.raw_user_meta_data->>'full_name'),
    u.raw_user_meta_data->>'avatar_url',
    p_role,
    p_institution
  FROM auth.users u
  WHERE u.id = v_uid
  ON CONFLICT (id) DO UPDATE SET
    -- An existing role always wins — this is the immutability guarantee.
    role        = COALESCE(profiles.role, EXCLUDED.role),
    full_name   = COALESCE(NULLIF(EXCLUDED.full_name, ''), profiles.full_name),
    institution = EXCLUDED.institution;

  SELECT role INTO v_role FROM public.profiles WHERE id = v_uid;
  RETURN v_role;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION public.set_profile_role(user_role, TEXT, TEXT) TO authenticated;
