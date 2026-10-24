-- LEGADO: solo para 001_nclub.sql. Las tablas en español usan nclub_completo.sql.
-- Only members and administrators use the app. Visitors remain managed by ADMIN.
-- Apply after 001_nclub.sql, including on existing installations.
begin;

create function private.can_use_app() returns boolean
language sql stable security definer set search_path='' as $$
  select exists (
    select 1 from public.profiles
    where auth_user_id=(select auth.uid()) and role in ('VIP','REGULAR','ADMIN')
  )
$$;
revoke all on function private.can_use_app() from public;
grant execute on function private.can_use_app() to authenticated;

-- Also prevents visitor accounts from issuing their own QR through the RPC.
-- ADMIN can still issue visitor QR codes and create invitations and work orders.
create or replace function private.profile_id() returns uuid
language sql stable security definer set search_path='' as $$
  select id from public.profiles
  where auth_user_id=(select auth.uid()) and role in ('VIP','REGULAR','ADMIN')
$$;

-- Restrictive policies apply in addition to the existing ownership/admin rules.
do $$
declare table_name text;
begin
  foreach table_name in array array[
    'profiles','services','reservations','credentials',
    'invitations','work_assignments','access_events'
  ] loop
    execute format(
      'create policy app_accounts_only on public.%I as restrictive for all to authenticated using ((select private.can_use_app())) with check ((select private.can_use_app()))',
      table_name
    );
  end loop;
end $$;

commit;
