-- Cognira Database Security: Row Level Security (RLS) Policies
-- Run this in your Supabase SQL Editor.

-- 0. Enable RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 1. Drop any old / conflicting policies
DROP POLICY IF EXISTS "Allow users to read their own profile"              ON public.profiles;
DROP POLICY IF EXISTS "Allow users to insert or update their own profile"  ON public.profiles;
DROP POLICY IF EXISTS "Allow users to insert their own profile"            ON public.profiles;
DROP POLICY IF EXISTS "Allow users to update their own profile"            ON public.profiles;
DROP POLICY IF EXISTS "profiles_select_own"                                ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own"                                ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own"                                ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own_metadata_only"                  ON public.profiles;

-- 2. SELECT: users can only read their own row
CREATE POLICY "profiles_select_own"
ON public.profiles
FOR SELECT
TO authenticated
USING (auth.uid() = id);

-- 3. INSERT: users can create their own profile row
--    (also fired by upsert_profile_on_login RPC on first signup)
CREATE POLICY "profiles_insert_own"
ON public.profiles
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = id);

-- 4. UPDATE: ownership check only — no role conditions needed
--    The role column is protected separately via column-level privilege (see below)
CREATE POLICY "profiles_update_own"
ON public.profiles
FOR UPDATE
TO authenticated
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);

-- ══════════════════════════════════════════════════════════
--  COLUMN-LEVEL PROTECTION: replaces the need for a trigger
--  Revokes the ability to UPDATE the role column from all
--  authenticated (anon-key) users at the Postgres level.
--
--  The upsert_profile_on_login RPC (SECURITY DEFINER) is
--  exempt — it runs as the DB owner and can still set role
--  on first INSERT. Its ON CONFLICT UPDATE clause intentionally
--  excludes role, so it never overwrites an existing role.
-- ══════════════════════════════════════════════════════════
REVOKE UPDATE (role) ON public.profiles FROM authenticated;
