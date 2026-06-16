/**
 * types/database.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Single source of truth for all database-related types.
 *
 * Mirrors public.profiles and related enums from supabase/schema.sql.
 * Import from here instead of defining types inside individual pages.
 *
 * Usage:
 *   import type { UserRole, Profile, OnboardingRole } from '@/types/database'
 */

// ── Enums ──────────────────────────────────────────────────────────────────────

/** Mirrors the `user_role` Postgres enum in supabase/schema.sql */
export type UserRole = 'student' | 'faculty' | 'admin'

// ── Table: public.profiles ─────────────────────────────────────────────────────

/** Full shape of a row in public.profiles */
export interface Profile {
  /** UUID — references auth.users.id */
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  /** NULL means user hasn't completed onboarding yet */
  role: UserRole | null
  /** Stores institution + extra profile metadata as a pipe-separated string */
  institution: string | null
  created_at: string
}

/** Partial shape used when reading only the role during route/proxy checks */
export type ProfileRoleSnapshot = Pick<Profile, 'id' | 'role'>

/**
 * Role the user picks on the onboarding screen.
 * Subset of UserRole — admins are assigned manually, never through onboarding.
 */
export type OnboardingRole = 'student' | 'faculty'

// ── RPC argument types ─────────────────────────────────────────────────────────

/** Arguments passed to the upsert_profile_on_login Postgres RPC */
export interface UpsertProfileOnLoginArgs {
  p_id: string
  p_email: string
  p_full_name: string | null
  p_avatar: string | null
}
