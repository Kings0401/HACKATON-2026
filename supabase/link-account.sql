-- LEGADO: para personas usar vincular_cuenta.sql, no este archivo.
-- Create the account using Supabase Dashboard > Authentication > Users > Add user.
-- Copy its UUID; replace the two example values below. Run as project owner.
-- Use one transaction per account. Never accept role or UUID from client metadata.
begin;
do $$
declare
  account_uuid uuid := '0f0f1658-f2eb-4b3d-b7f9-78415af41e6c'; -- Auth user UUID
  profile_email text := 'gabriela@nclub.demo'; -- existing seed profile email
begin
  if not exists(select 1 from auth.users where id=account_uuid) then raise exception 'Create the Auth account first and paste its real UUID.'; end if;
  update public.profiles set auth_user_id=account_uuid where email=profile_email and role in ('VIP','REGULAR','ADMIN');
  if not found then raise exception 'Only VIP, REGULAR and ADMIN profiles can have an app account. Check the profile email and category.'; end if;
end $$;
commit;
