-- LEGADO: esquema anterior en inglés. Para las tablas personas/membresias/reservas
-- usar ../nclub_completo.sql según supabase/README.md. No ejecutar ambos esquemas.
-- N Club World MVP. Apply once using the Supabase SQL Editor (project owner).
begin;
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists btree_gist with schema extensions;
create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;
set local search_path = public, extensions;

create table public.profiles (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique references auth.users(id) on delete set null,
  public_id text not null unique default ('NC-' || upper(substr(replace(gen_random_uuid()::text,'-',''),1,12))),
  full_name text not null check (length(trim(full_name)) between 3 and 100),
  email text unique,
  role text not null check (role in ('VIP','REGULAR','GUEST','STAFF','EXTERNAL','ADMIN')),
  membership_status text not null default 'active' check (membership_status in ('active','inactive','suspended')),
  position text,
  created_at timestamptz not null default now()
);
create table public.services (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text not null,
  category text not null check (category in ('golf','restaurant','lounge')),
  vip_only boolean not null default false,
  active boolean not null default true,
  image text
);
create table public.reservations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id),
  service_id uuid not null references public.services(id),
  reservation_date date not null,
  start_time time not null,
  end_time time not null,
  status text not null default 'confirmed' check (status in ('confirmed','cancelled')),
  created_at timestamptz not null default now(),
  check (end_time > start_time),
  -- Atomic exclusion prevents concurrent bookings and all overlapping intervals.
  exclude using gist (service_id with =, tsrange(reservation_date+start_time,reservation_date+end_time,'[)') with &&) where (status='confirmed'),
  exclude using gist (user_id with =, tsrange(reservation_date+start_time,reservation_date+end_time,'[)') with &&) where (status='confirmed')
);
create table public.credentials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id),
  token_hash text not null unique check (length(token_hash)=64),
  credential_type text not null check (credential_type in ('MEMBER','INVITATION','SHIFT','EXTERNAL_ORDER')),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
create table public.invitations (
  id uuid primary key default gen_random_uuid(),
  guest_id uuid not null references public.profiles(id),
  host_id uuid not null references public.profiles(id),
  visit_date date not null,
  valid_from timestamptz not null,
  valid_until timestamptz not null,
  destination text not null check (destination in ('RESTAURANT','GOLF_RECEPTION')),
  status text not null default 'active' check (status in ('active','revoked')),
  check (valid_until>valid_from)
);
create table public.work_assignments (
  id uuid primary key default gen_random_uuid(),
  worker_id uuid not null references public.profiles(id),
  company text not null check (length(trim(company)) between 2 and 100),
  assignment_type text not null check (assignment_type in ('SHIFT','EXTERNAL_ORDER')),
  valid_from timestamptz not null,
  valid_until timestamptz not null,
  authorized_zone text not null,
  status text not null default 'active' check (status in ('active','revoked')),
  check (valid_until>valid_from),
  check ((assignment_type='SHIFT' and authorized_zone in ('KITCHEN','RECEPTION','GOLF_OPERATIONS')) or
         (assignment_type='EXTERNAL_ORDER' and authorized_zone in ('MAINTENANCE','SERVICE_ENTRANCE')))
);
create table public.access_events (
  id uuid primary key default gen_random_uuid(),
  visitor_id uuid not null references public.profiles(id),
  role text not null check (role in ('VIP','REGULAR','GUEST','STAFF','EXTERNAL','ADMIN')),
  event_type text not null,
  access_status text not null check (access_status in ('pending','authorized','denied','review')),
  destination text,
  robot_target text not null check (robot_target in ('robot1','robot2')),
  simulation boolean not null default true,
  created_at timestamptz not null default now(),
  check (access_status<>'authorized' or destination is not null),
  check (event_type<>'vip_handoff' or (role='VIP' and access_status='authorized' and robot_target='robot2'))
);

create index profiles_role_status on public.profiles(role,membership_status);
create index reservations_user_date on public.reservations(user_id,reservation_date);
create index reservations_resource_date on public.reservations(service_id,reservation_date) where status='confirmed';
create index credentials_user on public.credentials(user_id);
create index invitations_guest on public.invitations(guest_id,valid_until);
create index invitations_host on public.invitations(host_id);
create index assignments_worker on public.work_assignments(worker_id,valid_until);
create index access_events_visitor_date on public.access_events(visitor_id,created_at desc);
create index access_events_recent on public.access_events(created_at desc);

-- SECURITY DEFINER helpers avoid recursive profile RLS; they expose only the caller's identity.
create function private.profile_id() returns uuid language sql stable security definer set search_path='' as $$
  select id from public.profiles where auth_user_id=(select auth.uid())
$$;
create function private.is_admin() returns boolean language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.profiles where auth_user_id=(select auth.uid()) and role='ADMIN' and membership_status='active')
$$;
revoke all on function private.profile_id(), private.is_admin() from public;
grant execute on function private.profile_id(), private.is_admin() to authenticated;

alter table public.profiles enable row level security;
alter table public.services enable row level security;
alter table public.reservations enable row level security;
alter table public.credentials enable row level security;
alter table public.invitations enable row level security;
alter table public.work_assignments enable row level security;
alter table public.access_events enable row level security;

-- Explicit grants, including for projects which do not auto-grant new tables.
revoke all on public.profiles,public.services,public.reservations,public.credentials,public.invitations,public.work_assignments,public.access_events from anon,authenticated;
grant select on public.profiles,public.services,public.reservations,public.invitations,public.work_assignments,public.access_events to authenticated;
grant update(full_name,membership_status) on public.profiles to authenticated;
grant insert(user_id,service_id,reservation_date,start_time,end_time,status) on public.reservations to authenticated;
grant update(service_id,reservation_date,start_time,end_time,status,user_id) on public.reservations to authenticated;
grant update(status) on public.invitations,public.work_assignments to authenticated;
grant all on public.profiles,public.services,public.reservations,public.credentials,public.invitations,public.work_assignments,public.access_events to service_role;

create policy profiles_read on public.profiles for select to authenticated using (id=(select private.profile_id()) or (select private.is_admin()));
create policy profiles_admin_update on public.profiles for update to authenticated using ((select private.is_admin())) with check ((select private.is_admin()));
create policy services_read on public.services for select to authenticated using (active or (select private.is_admin()));
create policy reservations_read on public.reservations for select to authenticated using (user_id=(select private.profile_id()) or (select private.is_admin()));
create policy reservations_insert on public.reservations for insert to authenticated with check (user_id=(select private.profile_id()));
create policy reservations_update on public.reservations for update to authenticated using (user_id=(select private.profile_id()) or (select private.is_admin())) with check (user_id=(select private.profile_id()) or (select private.is_admin()));
create policy invitations_read on public.invitations for select to authenticated using (guest_id=(select private.profile_id()) or host_id=(select private.profile_id()) or (select private.is_admin()));
create policy invitations_update on public.invitations for update to authenticated using ((select private.is_admin())) with check ((select private.is_admin()));
create policy assignments_read on public.work_assignments for select to authenticated using (worker_id=(select private.profile_id()) or (select private.is_admin()));
create policy assignments_update on public.work_assignments for update to authenticated using ((select private.is_admin())) with check ((select private.is_admin()));
create policy access_events_read on public.access_events for select to authenticated using (visitor_id=(select private.profile_id()) or (select private.is_admin()));
-- No browser INSERT/UPDATE/DELETE policy or grant for access_events or credentials.

create function private.enforce_reservation() returns trigger language plpgsql security definer set search_path='' as $$
declare p public.profiles; s public.services; local_now timestamp := now() at time zone 'America/Bogota';
begin
  if TG_OP='UPDATE' then
    if new.user_id<>old.user_id or new.created_at<>old.created_at then raise exception 'No puede cambiar el titular de una reserva.'; end if;
    if old.status='cancelled' then raise exception 'Una reserva cancelada no puede modificarse.'; end if;
    if new.status='cancelled' then
      if (new.service_id,new.reservation_date,new.start_time,new.end_time) is distinct from (old.service_id,old.reservation_date,old.start_time,old.end_time) then raise exception 'Cancele sin cambiar el horario.'; end if;
      return new;
    end if;
  elsif new.status<>'confirmed' then raise exception 'Estado de reserva no válido.';
  end if;
  select * into p from public.profiles where id=new.user_id;
  select * into s from public.services where id=new.service_id;
  if p.role not in ('VIP','REGULAR') or p.membership_status<>'active' then raise exception 'Se requiere una membresía activa.'; end if;
  if not s.active or (s.vip_only and p.role<>'VIP') then raise exception 'Su membresía no incluye este servicio.'; end if;
  if new.reservation_date+new.start_time <= local_now or new.reservation_date > local_now::date+90 then raise exception 'Seleccione una fecha futura dentro de los próximos 90 días.'; end if;
  if new.start_time<'08:00'::time or new.end_time>'18:00'::time or extract(minute from new.start_time)<>0 or extract(second from new.start_time)<>0 or new.end_time<>new.start_time+interval '1 hour' then raise exception 'Horario no permitido: bloques de una hora entre 08:00 y 18:00.'; end if;
  return new;
end $$;
create trigger enforce_reservation before insert or update on public.reservations for each row execute function private.enforce_reservation();

create function private.enforce_authorization() returns trigger language plpgsql security definer set search_path='' as $$
declare target_role text; host_valid boolean;
begin
  if TG_TABLE_NAME='invitations' then
    select role into target_role from public.profiles where id=new.guest_id;
    select (role in ('VIP','REGULAR') and membership_status='active') into host_valid from public.profiles where id=new.host_id;
    if target_role<>'GUEST' or not coalesce(host_valid,false) then raise exception 'Invitado o anfitrión no válido.'; end if;
    if new.visit_date<>(new.valid_from at time zone 'America/Bogota')::date then raise exception 'La fecha de visita debe coincidir con la vigencia.'; end if;
  else
    select role into target_role from public.profiles where id=new.worker_id;
    if (new.assignment_type='SHIFT' and target_role<>'STAFF') or (new.assignment_type='EXTERNAL_ORDER' and target_role<>'EXTERNAL') then raise exception 'El tipo de trabajo no coincide con la identidad.'; end if;
  end if;
  return new;
end $$;
create trigger enforce_invitation before insert or update on public.invitations for each row execute function private.enforce_authorization();
create trigger enforce_assignment before insert or update on public.work_assignments for each row execute function private.enforce_authorization();

create function public.get_availability(p_service uuid,p_date date) returns table(start_time time,end_time time)
language plpgsql stable security definer set search_path='' as $$
declare p public.profiles; s public.services;
begin
  select * into p from public.profiles where auth_user_id=auth.uid();
  select * into s from public.services where id=p_service;
  if p.id is null or p.membership_status<>'active' or (p.role not in ('VIP','REGULAR','ADMIN')) or s.id is null or not s.active or (s.vip_only and p.role not in ('VIP','ADMIN')) then raise exception 'No autorizado para consultar este servicio.'; end if;
  return query select r.start_time,r.end_time from public.reservations r where r.service_id=p_service and r.reservation_date=p_date and r.status='confirmed';
end $$;

-- Tokens are generated on the server, stored only as SHA-256, and returned once.
create function public.issue_credential(p_user_id uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.profiles; token text; expiry timestamptz; kind text;
begin
  if auth.uid() is null or (p_user_id is distinct from private.profile_id() and not private.is_admin()) then raise exception 'No autorizado para emitir esta credencial.'; end if;
  select * into p from public.profiles where id=p_user_id for update;
  if p.id is null or p.membership_status<>'active' then raise exception 'Identidad inactiva.'; end if;
  if p.role in ('VIP','REGULAR') then kind:='MEMBER'; expiry:=now()+interval '1 hour';
  elsif p.role='GUEST' then
    kind:='INVITATION';
    select least(i.valid_until,greatest(i.valid_from,now())+interval '24 hours') into expiry from public.invitations i join public.profiles host on host.id=i.host_id where i.guest_id=p.id and i.status='active' and i.valid_until>now() and host.membership_status='active' and host.role in ('VIP','REGULAR') order by i.valid_until desc limit 1;
  elsif p.role in ('STAFF','EXTERNAL') then
    kind:=case when p.role='STAFF' then 'SHIFT' else 'EXTERNAL_ORDER' end;
    select least(w.valid_until,greatest(w.valid_from,now())+interval '24 hours') into expiry from public.work_assignments w where w.worker_id=p.id and w.assignment_type=kind and w.status='active' and w.valid_until>now() order by w.valid_until desc limit 1;
  else raise exception 'La cuenta administrativa no es una credencial de visitante.';
  end if;
  if expiry is null or expiry<=now() then raise exception 'No hay invitación, turno u orden vigente.'; end if;
  token:=encode(extensions.gen_random_bytes(32),'hex');
  update public.credentials set revoked_at=now() where user_id=p.id and revoked_at is null;
  insert into public.credentials(user_id,token_hash,credential_type,expires_at) values(p.id,encode(extensions.digest(token,'sha256'),'hex'),kind,expiry);
  return jsonb_build_object('token',token,'expires_at',expiry);
end $$;

-- Atomic visitor + authorization + credential creation. Only active ADMIN.
create function public.admin_create_visitor(p_name text,p_role text,p_host uuid,p_company text,p_from timestamptz,p_until timestamptz,p_zone text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare person_id uuid; credential jsonb;
begin
  if not private.is_admin() then raise exception 'Solo administradores activos.'; end if;
  if p_role not in ('GUEST','STAFF','EXTERNAL') then raise exception 'Categoría no válida para este formulario.'; end if;
  if p_from>=p_until or p_until<=now() or p_until>p_from+interval '7 days' then raise exception 'Vigencia no válida (máximo 7 días).'; end if;
  insert into public.profiles(full_name,role,position) values(trim(p_name),p_role,case when p_role='STAFF' then 'Personal del club' when p_role='EXTERNAL' then p_company end) returning id into person_id;
  if p_role='GUEST' then
    insert into public.invitations(guest_id,host_id,visit_date,valid_from,valid_until,destination) values(person_id,p_host,(p_from at time zone 'America/Bogota')::date,p_from,p_until,p_zone);
  else
    insert into public.work_assignments(worker_id,company,assignment_type,valid_from,valid_until,authorized_zone) values(person_id,trim(p_company),case when p_role='STAFF' then 'SHIFT' else 'EXTERNAL_ORDER' end,p_from,p_until,p_zone);
  end if;
  credential:=public.issue_credential(person_id);
  return credential || jsonb_build_object('user_id',person_id);
end $$;

revoke all on function public.get_availability(uuid,date),public.issue_credential(uuid),public.admin_create_visitor(text,text,uuid,text,timestamptz,timestamptz,text) from public,anon;
grant execute on function public.get_availability(uuid,date),public.issue_credential(uuid),public.admin_create_visitor(text,text,uuid,text,timestamptz,timestamptz,text) to authenticated;
revoke all on function private.enforce_reservation(),private.enforce_authorization() from public,anon,authenticated;

-- RLS still controls what each subscriber can see. No public broadcasts of private data.
do $$ declare t text; begin
  foreach t in array array['profiles','reservations','invitations','work_assignments','access_events'] loop
    if not exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename=t) then
      execute format('alter publication supabase_realtime add table public.%I',t);
    end if;
  end loop;
end $$;
commit;
