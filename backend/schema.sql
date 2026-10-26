-- RAG storage setup and upgrade. Run in the Supabase SQL Editor after 01-06.
-- Safe to rerun: preserves existing rows, 768-dimensional vectors and RLS policies.
-- CREATE TABLE IF NOT EXISTS alone does not upgrade an existing table.
begin;

create extension if not exists vector with schema extensions;

create table if not exists public.document_chunks (
    id text primary key default gen_random_uuid()::text,
    node_id text unique not null,
    parent_id text,
    source_id uuid not null,
    owner_id uuid references auth.users(id) on delete cascade,
    file_name text not null default '',
    page_start integer,
    page_end integer,
    chunk_index integer not null default 0,
    content text not null,
    embedding extensions.vector(768),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- Upgrade the older table in place, without dropping data or changing vector size.
alter table public.document_chunks
    add column if not exists node_id text,
    add column if not exists parent_id text,
    add column if not exists owner_id uuid references auth.users(id) on delete cascade,
    add column if not exists file_name text not null default '',
    add column if not exists page_start integer,
    add column if not exists page_end integer,
    add column if not exists chunk_index integer not null default 0;

-- Older chunks used id as their node identifier. Keep those identifiers stable.
update public.document_chunks set node_id = id::text where node_id is null;
alter table public.document_chunks alter column node_id set not null;

-- Parent contexts have no vector; only their children participate in search.
alter table public.document_chunks alter column embedding drop not null;

do $$
declare
    v_id_type text;
    v_embedding_type text;
begin
    select format_type(atttypid, atttypmod) into v_id_type
    from pg_attribute
    where attrelid = 'public.document_chunks'::regclass and attname = 'id';

    if v_id_type = 'text' then
        alter table public.document_chunks alter column id set default gen_random_uuid()::text;
    elsif v_id_type = 'uuid' then
        alter table public.document_chunks alter column id set default gen_random_uuid();
    end if;

    select format_type(atttypid, atttypmod) into v_embedding_type
    from pg_attribute
    where attrelid = 'public.document_chunks'::regclass and attname = 'embedding';

    if v_embedding_type not like '%vector(768)' then
        raise exception 'Expected vector(768), found %. Re-embedding requires a separate migration.', v_embedding_type;
    end if;
end;
$$;

create unique index if not exists document_chunks_node_id_key
    on public.document_chunks (node_id);
create index if not exists document_chunks_source_id_idx
    on public.document_chunks (source_id);
create index if not exists document_chunks_parent_id_idx
    on public.document_chunks (parent_id);
create index if not exists document_chunks_embedding_idx
    on public.document_chunks using hnsw (embedding extensions.vector_cosine_ops)
    with (m = 16, ef_construction = 64);

alter table public.document_chunks enable row level security;
-- The Python pipeline uses the server-side service role. Existing owner policies
-- are preserved; a fresh installation does not grant browser access to chunks.
grant select, insert, update, delete on public.document_chunks to service_role;

create or replace function public.match_document_chunks (
    query_embedding extensions.vector(768),
    match_count integer default 5,
    filter_source_ids text[] default '{}'
) returns table (
    id text,
    node_id text,
    parent_id text,
    source_id text,
    content text,
    metadata jsonb,
    similarity double precision
)
language sql stable security invoker
set search_path = public, extensions, pg_temp
as $$
    select
        dc.id::text,
        dc.node_id,
        dc.parent_id,
        dc.source_id::text,
        dc.content,
        dc.metadata,
        (1 - (dc.embedding <=> query_embedding))::double precision
    from public.document_chunks dc
    where dc.embedding is not null
        and dc.source_id::text = any(filter_source_ids)
    order by dc.embedding <=> query_embedding
    limit greatest(0, least(match_count, 100));
$$;

revoke execute on function public.match_document_chunks(extensions.vector, integer, text[])
    from public, anon, authenticated;
grant execute on function public.match_document_chunks(extensions.vector, integer, text[])
    to service_role;

-- Make the new column and RPC visible to the REST API after commit.

-- Assessment platform and authenticated chunk replacement.
create table if not exists public.assessments (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users(id),
    title text not null check(length(title) between 1 and 200),
    config jsonb not null default '{}',
    questions jsonb not null check(jsonb_typeof(questions) = 'array' and jsonb_array_length(questions) between 1 and 30),
    status text not null default 'draft' check(status in ('draft','published','archived')),
    join_code text unique not null,
    adaptive boolean not null default true,
    duration_seconds integer check(duration_seconds between 60 and 86400),
    closes_at timestamptz,
    created_at timestamptz not null default now(),
    published_at timestamptz,
    version integer not null default 1
);
create table if not exists public.assessment_enrollments (
    assessment_id uuid not null references public.assessments(id) on delete cascade,
    student_id uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key(assessment_id,student_id)
);
create table if not exists public.assessment_attempts (
    id uuid primary key default gen_random_uuid(),
    assessment_id uuid not null references public.assessments(id),
    student_id uuid not null references auth.users(id),
    status text not null default 'active' check(status in ('active','submitted')),
    started_at timestamptz not null default now(),
    expires_at timestamptz,
    submitted_at timestamptz,
    presented jsonb not null default '[]',
    answers jsonb not null default '{}',
    draft_answer integer check(draft_answer between 0 and 3),
    draft_answers jsonb not null default '[]',
    mastery jsonb not null default '{}',
    score integer,
    total integer not null check(total between 1 and 30),
    version integer not null default 1,
    unique(assessment_id,student_id)
);
alter table public.assessment_attempts add column if not exists draft_answers jsonb not null default '[]';
alter table public.assessment_attempts add column if not exists mastery jsonb not null default '{}';
create table if not exists public.assessment_audit (
    id uuid primary key default gen_random_uuid(),
    actor_id uuid not null references auth.users(id),
    action text not null,
    target_id uuid not null,
    created_at timestamptz not null default now()
);
create index if not exists assessments_owner_created_idx on public.assessments(owner_id,created_at desc);
create index if not exists attempts_student_submitted_idx on public.assessment_attempts(student_id,submitted_at desc);
create index if not exists attempts_assessment_idx on public.assessment_attempts(assessment_id);
create index if not exists enrollments_student_idx on public.assessment_enrollments(student_id);
create index if not exists audit_actor_created_idx on public.assessment_audit(actor_id,created_at desc);
alter table public.profiles add column if not exists suspended boolean not null default false;

-- Answer keys are intentionally unavailable to browser database clients.
do $$
declare v_table text;
begin
    foreach v_table in array array['assessments','assessment_attempts','assessment_enrollments','assessment_audit'] loop
        execute format('alter table public.%I enable row level security',v_table);
        execute format('revoke all on public.%I from anon, authenticated',v_table);
        execute format('grant select,insert,update,delete on public.%I to service_role',v_table);
        execute format('drop policy if exists backend_access on public.%I',v_table);
        execute format('create policy backend_access on public.%I for all to service_role using (true) with check (true)',v_table);
    end loop;
end;
$$;

create or replace function public.replace_document_chunks(p_source_id uuid,p_owner_id uuid,p_rows jsonb)
returns integer language plpgsql security invoker
set search_path=public,extensions,pg_temp as $$
declare inserted integer;
begin
    if p_owner_id is null or jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) > 2000 then
        raise exception 'Invalid chunk replacement request';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_source_id::text,0));
    delete from public.document_chunks where source_id::text=p_source_id::text and owner_id=p_owner_id;
    insert into public.document_chunks(node_id,parent_id,source_id,owner_id,content,embedding,metadata,file_name,chunk_index,page_start,page_end)
    select r.node_id,r.parent_id,p_source_id,p_owner_id,r.content,
           case when r.embedding is null or r.embedding='null'::jsonb then null else r.embedding::text::extensions.vector(768) end,
           coalesce(r.metadata,'{}'::jsonb),coalesce(r.file_name,''),coalesce(r.chunk_index,0),r.page_start,r.page_end
    from jsonb_to_recordset(p_rows) as r(node_id text,parent_id text,content text,embedding jsonb,metadata jsonb,file_name text,chunk_index integer,page_start integer,page_end integer);
    get diagnostics inserted = row_count;
    return inserted;
end;
$$;
revoke execute on function public.replace_document_chunks(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.replace_document_chunks(uuid,uuid,jsonb) to service_role;
create index if not exists chunks_owner_source_idx on public.document_chunks(owner_id,source_id);

-- Older deployments may still expose the superseded retrieval RPC.
do $$
begin
    if to_regprocedure('public.match_chunks(extensions.vector,integer,double precision,uuid[],uuid)') is not null then
        alter function public.match_chunks(extensions.vector,integer,double precision,uuid[],uuid) set search_path=public,extensions,pg_temp;
        revoke execute on function public.match_chunks(extensions.vector,integer,double precision,uuid[],uuid) from public,anon,authenticated;
        grant execute on function public.match_chunks(extensions.vector,integer,double precision,uuid[],uuid) to service_role;
    end if;
end;
$$;

-- Profile roles can only be selected during onboarding or changed by the admin API.
revoke insert,update on public.profiles from authenticated;
grant insert(id,email,full_name,avatar_url,institution) on public.profiles to authenticated;
grant update(full_name,avatar_url,institution) on public.profiles to authenticated;
create or replace function public.upsert_profile_on_login(p_id uuid,p_email text,p_full_name text,p_avatar text)
returns void language plpgsql security definer set search_path='' as $$
begin
    if auth.uid() is null or p_id <> auth.uid() then raise exception 'Not authorized'; end if;
    insert into public.profiles(id,email,full_name,avatar_url)
    select id,email,coalesce(nullif(p_full_name,''),raw_user_meta_data->>'full_name'),p_avatar
    from auth.users where id=auth.uid()
    on conflict(id) do update set full_name=excluded.full_name,avatar_url=excluded.avatar_url;
end;
$$;
create or replace function public.set_profile_role(p_role public.user_role,p_full_name text,p_institution text)
returns public.user_role language plpgsql security definer set search_path='' as $$
declare v_role public.user_role;
begin
    if auth.uid() is null then raise exception 'Not signed in'; end if;
    if p_role is null or p_role not in ('student','faculty') then raise exception 'Invalid onboarding role'; end if;
    insert into public.profiles(id,email,full_name,avatar_url,role,institution)
    select id,email,coalesce(nullif(p_full_name,''),raw_user_meta_data->>'full_name'),
           raw_user_meta_data->>'avatar_url',p_role,p_institution from auth.users where id=auth.uid()
    on conflict(id) do update set role=coalesce(profiles.role,excluded.role),
        full_name=coalesce(nullif(excluded.full_name,''),profiles.full_name),institution=excluded.institution;
    select role into v_role from public.profiles where id=auth.uid();
    return v_role;
end;
$$;
revoke execute on function public.upsert_profile_on_login(uuid,text,text,text) from public,anon;
revoke execute on function public.set_profile_role(public.user_role,text,text) from public,anon;
grant execute on function public.upsert_profile_on_login(uuid,text,text,text) to authenticated;
grant execute on function public.set_profile_role(public.user_role,text,text) to authenticated;
alter function public.handle_new_user() set search_path=public,pg_temp;
revoke execute on function public.handle_new_user() from public,anon,authenticated;

-- Storage paths are scoped to the signed-in account, including deletion.
drop policy if exists "Allow faculty to upload files" on storage.objects;
drop policy if exists "Allow faculty to view files" on storage.objects;
drop policy if exists "Allow faculty to delete files" on storage.objects;
drop policy if exists faculty_documents_owned on storage.objects;
create policy faculty_documents_owned on storage.objects for all to authenticated
using (
    bucket_id='faculty-documents' and (storage.foldername(name))[1]=auth.uid()::text
    and exists(select 1 from public.profiles p where p.id=auth.uid() and p.role in ('faculty','admin') and not p.suspended)
)
with check (
    bucket_id='faculty-documents' and (storage.foldername(name))[1]=auth.uid()::text
    and exists(select 1 from public.profiles p where p.id=auth.uid() and p.role in ('faculty','admin') and not p.suspended)
);
update storage.buckets set public=false,file_size_limit=5242880,
allowed_mime_types=array['application/pdf','application/msword','application/vnd.ms-powerpoint',
'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
'application/vnd.openxmlformats-officedocument.presentationml.presentation','image/png','image/jpeg','application/octet-stream']
where id='faculty-documents';

notify pgrst, 'reload schema';
commit;

