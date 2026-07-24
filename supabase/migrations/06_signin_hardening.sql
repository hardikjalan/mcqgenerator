-- Cognira — Sign-in hardening
-- Run this AFTER 05_onboarding.sql in your Supabase SQL Editor.
-- Safe to run more than once.
--
-- Fixes two ways a first-time sign-in could leave an account stranded:
--
--   1. set_profile_role only ever ran an UPDATE. If the profile row didn't
--      exist yet — the trigger hadn't fired, or it failed — the UPDATE matched
--      zero rows and reported success. The role stayed NULL, so the proxy sent
--      the user straight back to onboarding, forever, with no error shown.
--      It now creates the row when it's missing.
--
--   2. Neither function returned anything, so the app couldn't tell a real
--      save from a silent no-op. set_profile_role now returns the role that
--      ended up stored, and the onboarding screen checks it.
--
-- The "role is set once and never changed" rule is unchanged: the ON CONFLICT
-- branch keeps any existing role via COALESCE.

-- ── 1. Make role assignment create the row if it's missing ────────────────────
-- The return type changes, so the old signature has to go first.
DROP FUNCTION IF EXISTS public.set_profile_role(user_role, TEXT, TEXT);

CREATE FUNCTION public.set_profile_role(
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

-- ── 2. Make sure the app is allowed to call both functions ────────────────────
GRANT EXECUTE ON FUNCTION public.set_profile_role(user_role, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.upsert_profile_on_login(UUID, TEXT, TEXT, TEXT) TO authenticated;

-- ── 3. Backfill any account that got stranded without a profile row ───────────
-- Role stays NULL, so these users land on onboarding and pick one normally.
INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
SELECT
  u.id,
  u.email,
  u.raw_user_meta_data->>'full_name',
  u.raw_user_meta_data->>'avatar_url',
  NULL
FROM auth.users u
LEFT JOIN public.profiles p ON p.id = u.id
WHERE p.id IS NULL
  AND u.email IS NOT NULL
ON CONFLICT (id) DO NOTHING;
