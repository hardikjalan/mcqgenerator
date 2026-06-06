-- Cognira Database Triggers
-- Run this SECOND in your Supabase SQL Editor (requires schema.sql to be run first).

-- 1. Create helper function to automatically link new signups into profiles
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, avatar_url, role)
  VALUES (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url',
    CASE
      -- Developer override for testing
      WHEN new.email = 'hardikjalan2005@gmail.com' THEN 'faculty'::user_role
      -- Domain mapping
      WHEN new.email LIKE '%@vit.ac.in' THEN 'faculty'::user_role
      WHEN new.email LIKE '%@vitstudent.ac.in' THEN 'student'::user_role
      ELSE NULL
    END
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    avatar_url = EXCLUDED.avatar_url,
    role = COALESCE(profiles.role, EXCLUDED.role);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Link helper function as an after-insert trigger on auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
