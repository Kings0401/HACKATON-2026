-- Crear primero la cuenta en Authentication > Users > Add user.
-- Reemplazar los dos valores. Ejecutar como propietario, una cuenta por vez.
-- Miembro VIP: VIP001. Miembro regular: REG001. Administrador demo: ADMIN001.
-- Invitados, personal y externos NO se vinculan a Supabase Auth.
begin;
do $$
declare
  usuario_auth uuid := '00000000-0000-0000-0000-000000000000';
  persona text := 'VIP001';
begin
  if not exists(select 1 from auth.users where id=usuario_auth) then
    raise exception 'Crea la cuenta de Auth y pega su UUID real.';
  end if;
  if exists(select 1 from public.personas where id=persona and auth_user_id is not null and auth_user_id<>usuario_auth) then
    raise exception 'Esta persona ya está vinculada a otra cuenta. Revisa la asociación antes de cambiarla.';
  end if;
  update public.personas set auth_user_id=usuario_auth
  where id=persona and categoria in ('VIP','REGULAR','ADMIN');
  if not found then raise exception 'Solo VIP, REGULAR y ADMIN pueden tener cuenta de aplicación. Revisa el ID de persona.'; end if;
end $$;
commit;
