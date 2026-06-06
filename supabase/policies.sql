-- Cognira Database Security: Row Level Security (RLS) Policies
-- Run this after schema.sql.

-- 1. Enable Row Level Security (RLS) on tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 2. Create policy to allow users to read their own profile
DROP POLICY IF EXISTS "Allow users to read their own profile" ON public.profiles;
CREATE POLICY "Allow users to read their own profile"
ON public.profiles
FOR SELECT
USING (auth.uid() = id);

-- 3. Create policy to allow users to insert or update their own profile
DROP POLICY IF EXISTS "Allow users to insert or update their own profile" ON public.profiles;
CREATE POLICY "Allow users to insert or update their own profile"
ON public.profiles
FOR ALL
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);
