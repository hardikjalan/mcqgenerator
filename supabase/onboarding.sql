-- Cognira — Onboarding SQL
-- Run this in your Supabase SQL Editor (Settings → SQL Editor).
-- Safe to run multiple times — all statements are idempotent.

-- ── 1. Add institution column to profiles ─────────────────────────────────────
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS institution TEXT;

-- ── 2. Drop any legacy trigger that blocks role updates ────────────────────────
--    Old versions of the codebase had a trigger that raised:
--    "role is immutable via client API" — this removes it.
DROP TRIGGER IF EXISTS protect_role_update  ON public.profiles;
DROP TRIGGER IF EXISTS prevent_role_change  ON public.profiles;
DROP TRIGGER IF EXISTS on_role_change       ON public.profiles;
DROP TRIGGER IF EXISTS immutable_role       ON public.profiles;
DROP FUNCTION IF EXISTS public.prevent_role_change();
DROP FUNCTION IF EXISTS public.protect_role_update();
DROP FUNCTION IF EXISTS public.enforce_immutable_role();

-- ── 3. Replace handle_new_user trigger — no domain logic, role always NULL ─────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
  VALUES (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url',
    NULL  -- role is always chosen in onboarding, never auto-assigned
  )
  ON CONFLICT (id) DO UPDATE SET
    email      = EXCLUDED.email,
    full_name  = EXCLUDED.full_name,
    avatar_url = EXCLUDED.avatar_url;
    -- role intentionally absent: preserves existing role on every re-login
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ── 4. New RPC: set_profile_role ───────────────────────────────────────────────
--    Lets a user set their role exactly once (only fires when role IS NULL).
--    SECURITY DEFINER runs as the DB owner — bypasses column-level REVOKE.
--    The WHERE role IS NULL guard is the immutability enforcement.
CREATE OR REPLACE FUNCTION public.set_profile_role(
  p_role        user_role,
  p_full_name   TEXT,
  p_institution TEXT
)
RETURNS void AS $$
BEGIN
  UPDATE public.profiles
  SET
    role        = p_role,
    full_name   = COALESCE(NULLIF(p_full_name, ''), full_name),
    institution = p_institution
  WHERE id = auth.uid() AND role IS NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
