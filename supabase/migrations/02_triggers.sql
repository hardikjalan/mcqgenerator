-- Cognira Database Triggers & Functions
-- Run this AFTER 01_schema.sql in your Supabase SQL Editor.

-- ── Function 1: Auto-create profile on first signup ──────────────────────────
-- Fires on INSERT into auth.users (via trigger below).
-- Role is always NULL here — it is chosen by the user in onboarding.
-- ON CONFLICT preserves any existing role (safe for re-logins).
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
  VALUES (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url',
    NULL  -- role chosen during onboarding, never auto-assigned
  )
  ON CONFLICT (id) DO UPDATE SET
    email      = EXCLUDED.email,
    full_name  = EXCLUDED.full_name,
    avatar_url = EXCLUDED.avatar_url;
    -- role intentionally absent: preserves existing role on re-login
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ── Function 2: Metadata sync called by the auth callback ────────────────────
-- SECURITY DEFINER → runs as DB owner, bypasses RLS and column-level privileges.
--
-- Role is NOT a parameter — it is owned exclusively by the handle_new_user trigger.
-- This function only syncs non-sensitive metadata (name, avatar) on every login.
-- The role column is intentionally absent from both INSERT and ON CONFLICT UPDATE.
--
-- To change a user's role for testing, run directly in the Supabase SQL Editor:
--   UPDATE public.profiles SET role = 'faculty' WHERE email = 'you@example.com';
CREATE OR REPLACE FUNCTION public.upsert_profile_on_login(
  p_id        UUID,
  p_email     TEXT,
  p_full_name TEXT,
  p_avatar    TEXT
  -- no p_role: role is set once by the handle_new_user trigger, never by this function
)
RETURNS void AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, avatar_url)
  VALUES (p_id, p_email, p_full_name, p_avatar)
  ON CONFLICT (id) DO UPDATE SET
    email      = EXCLUDED.email,
    full_name  = EXCLUDED.full_name,
    avatar_url = EXCLUDED.avatar_url;
    -- role column deliberately absent — immutable after first assignment
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
