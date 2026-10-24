-- N CLUB: esquema compatible con las cinco tablas originales en español.
-- Ejecutar completo como propietario en Supabase SQL Editor (PostgreSQL 15+).
-- Puede repetirse. No borra personas, reservas, invitaciones ni permisos.
-- No ejecutar las migraciones antiguas 001/002 para esta instalación.
begin;
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists btree_gist with schema extensions;
create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;
set local search_path = public, extensions;

create table if not exists public.personas (
  id text primary key,
  nombre text not null,
  categoria text not null check (categoria in ('VIP','REGULAR','INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO','ADMIN')),
  grupo_facial text not null check (grupo_facial in ('member','non_member')),
  tipo_credencial text not null,
  codigo_credencial text not null unique,
  activo boolean not null default true,
  created_at timestamptz default now()
);
-- ADMIN es una cuenta administrativa, no una sexta clase de visitante.
alter table public.personas drop constraint if exists personas_categoria_check;
alter table public.personas add constraint personas_categoria_check
  check (categoria in ('VIP','REGULAR','INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO','ADMIN'));
alter table public.personas add column if not exists auth_user_id uuid references auth.users(id) on delete set null;
alter table public.personas add column if not exists email text;
alter table public.personas add column if not exists telefono text;
alter table public.personas add column if not exists tipo_documento text;
alter table public.personas add column if not exists numero_documento text;
alter table public.personas add column if not exists cargo text;
create unique index if not exists personas_auth_user_unique on public.personas(auth_user_id);
create unique index if not exists personas_documento_unico
  on public.personas(tipo_documento, numero_documento) where numero_documento is not null;
do $$ begin
  if not exists (select 1 from pg_constraint where conname='personas_documento_tipo_check' and conrelid='public.personas'::regclass) then
    alter table public.personas add constraint personas_documento_tipo_check
      check (tipo_documento is null or tipo_documento in ('CC','CE','PASAPORTE','OTRO'));
  end if;
  if not exists (select 1 from pg_constraint where conname='personas_documento_pareja_check' and conrelid='public.personas'::regclass) then
    alter table public.personas add constraint personas_documento_pareja_check
      check ((tipo_documento is null) = (numero_documento is null));
  end if;
  if not exists (select 1 from pg_constraint where conname='personas_documento_longitud_check' and conrelid='public.personas'::regclass) then
    alter table public.personas add constraint personas_documento_longitud_check
      check (numero_documento is null or length(numero_documento) between 5 and 30);
  end if;
end $$;

create table if not exists public.membresias (
  persona_id text primary key references public.personas(id),
  nivel text not null check (nivel in ('VIP','REGULAR')),
  estado text not null default 'ACTIVA' check (estado in ('ACTIVA','SUSPENDIDA')),
  vigencia_hasta timestamptz not null
);
create table if not exists public.reservas (
  id text primary key,
  persona_id text not null references public.personas(id),
  actividad text not null,
  destino text not null,
  fecha_inicio timestamptz not null,
  fecha_fin timestamptz not null,
  estado text not null default 'CONFIRMADA' check (estado in ('CONFIRMADA','CANCELADA')),
  check (fecha_fin > fecha_inicio)
);
create table if not exists public.invitaciones (
  codigo_qr text primary key,
  persona_id text not null references public.personas(id),
  anfitrion text not null,
  destino text not null,
  valido_desde timestamptz not null,
  valido_hasta timestamptz not null,
  estado text not null default 'ACTIVA' check (estado in ('ACTIVA','CANCELADA','UTILIZADA')),
  check (valido_hasta > valido_desde)
);
create table if not exists public.permisos_laborales (
  codigo_autorizacion text primary key,
  persona_id text not null references public.personas(id),
  tipo text not null check (tipo in ('PERSONAL_INTERNO','TRABAJADOR_EXTERNO')),
  actividad text not null,
  destino text not null,
  valido_desde timestamptz not null,
  valido_hasta timestamptz not null,
  requiere_acompanamiento boolean not null default false,
  estado text not null default 'ACTIVO' check (estado in ('ACTIVO','CANCELADO')),
  check (valido_hasta > valido_desde)
);

create table if not exists public.servicios (
  id text primary key,
  nombre text not null,
  descripcion text not null,
  categoria text not null check (categoria in ('GOLF','RESTAURANTE','LOUNGE')),
  destino text not null unique,
  exclusivo_vip boolean not null default false,
  activo boolean not null default true,
  imagen text
);
insert into public.servicios(id,nombre,descripcion,categoria,destino,exclusivo_vip,imagen)
select 'golf-'||n,'Campo de golf · Cancha '||n,'Un recorrido entre naturaleza y precisión.','GOLF',
  case when n=1 then 'Campo de golf' else 'Campo de golf · Cancha '||n end,false,'/images/course.jpg'
from generate_series(1,5) n on conflict do nothing;
insert into public.servicios(id,nombre,descripcion,categoria,destino,exclusivo_vip,imagen) values
('restaurant','Restaurante N Club','Sabores de temporada, momentos que permanecen.','RESTAURANTE','Restaurante principal',false,'/images/restaurant.jpg'),
('lounge','Lounge VIP','Un espacio reservado para lo extraordinario.','LOUNGE','VIP Lounge',true,'/images/lounge.jpg') on conflict do nothing;

alter table public.reservas add column if not exists servicio_id text references public.servicios(id);
alter table public.reservas add column if not exists created_at timestamptz not null default now();
alter table public.reservas alter column id set default ('RES-'||gen_random_uuid()::text);
alter table public.invitaciones add column if not exists anfitrion_id text references public.personas(id);
alter table public.invitaciones add column if not exists created_at timestamptz not null default now();
alter table public.permisos_laborales add column if not exists empresa text not null default 'N Club World';
alter table public.permisos_laborales add column if not exists created_at timestamptz not null default now();

-- Solo completar relaciones inequívocas. Un nombre de anfitrión no es una identidad.
update public.reservas r set servicio_id=s.id from public.servicios s
where r.servicio_id is null and r.destino=s.destino;
update public.invitaciones i set anfitrion_id=p.id from public.personas p
where i.anfitrion_id is null and i.anfitrion=p.nombre and p.categoria in ('VIP','REGULAR')
  and (select count(*) from public.personas x where x.nombre=i.anfitrion and x.categoria in ('VIP','REGULAR'))=1;

create table if not exists public.credenciales (
  id uuid primary key default gen_random_uuid(),
  persona_id text not null references public.personas(id),
  token_hash text not null unique check (length(token_hash)=64),
  tipo text not null check (tipo in ('MIEMBRO','INVITACION','TURNO','ORDEN_EXTERNA')),
  expira_en timestamptz not null,
  revocada_en timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists public.eventos_acceso (
  id uuid primary key default gen_random_uuid(),
  persona_id text not null references public.personas(id),
  categoria text not null check (categoria in ('VIP','REGULAR','INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO','ADMIN')),
  tipo_evento text not null,
  estado_acceso text not null check (estado_acceso in ('PENDIENTE','AUTORIZADO','DENEGADO','REVISION')),
  destino text,
  robot text not null check (robot in ('robot1','robot2')),
  simulacion boolean not null default true,
  created_at timestamptz not null default now(),
  check (estado_acceso<>'AUTORIZADO' or destino is not null),
  check (tipo_evento<>'vip_handoff' or (categoria='VIP' and estado_acceso='AUTORIZADO' and robot='robot2'))
);
create index if not exists reservas_persona_fecha on public.reservas(persona_id,fecha_inicio);
create index if not exists invitaciones_persona_vigencia on public.invitaciones(persona_id,valido_hasta);
create index if not exists invitaciones_anfitrion on public.invitaciones(anfitrion_id);
create index if not exists permisos_persona_vigencia on public.permisos_laborales(persona_id,valido_hasta);
create index if not exists credenciales_persona on public.credenciales(persona_id);
create index if not exists eventos_persona_fecha on public.eventos_acceso(persona_id,created_at desc);

-- Restricciones atómicas, incluso con dos reservas simultáneas.
-- Si ya hay solapamientos, la transacción se detiene sin borrar datos.
do $$ begin
  if not exists(select 1 from pg_constraint where conrelid='public.reservas'::regclass and conname='reservas_recurso_sin_solapamiento') then
    alter table public.reservas add constraint reservas_recurso_sin_solapamiento
      exclude using gist (servicio_id with =,tstzrange(fecha_inicio,fecha_fin,'[)') with &&)
      where (estado='CONFIRMADA' and servicio_id is not null);
  end if;
  if not exists(select 1 from pg_constraint where conrelid='public.reservas'::regclass and conname='reservas_persona_sin_solapamiento') then
    alter table public.reservas add constraint reservas_persona_sin_solapamiento
      exclude using gist (persona_id with =,tstzrange(fecha_inicio,fecha_fin,'[)') with &&)
      where (estado='CONFIRMADA');
  end if;
end $$;

create or replace function private.nclub_persona_id() returns text
language sql stable security definer set search_path='' as $$
  select id from public.personas where auth_user_id=(select auth.uid()) and categoria in ('VIP','REGULAR','ADMIN')
$$;
create or replace function private.nclub_es_admin() returns boolean
language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.personas where auth_user_id=(select auth.uid()) and categoria='ADMIN' and activo)
$$;
create or replace function private.nclub_miembro_vigente(p_id text) returns boolean
language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.personas p join public.membresias m on m.persona_id=p.id
    where p.id=p_id and p.activo and p.categoria in ('VIP','REGULAR') and m.nivel=p.categoria
      and m.estado='ACTIVA' and m.vigencia_hasta>now())
$$;
revoke all on function private.nclub_persona_id(),private.nclub_es_admin(),private.nclub_miembro_vigente(text) from public,anon;
grant execute on function private.nclub_persona_id(),private.nclub_es_admin() to authenticated;

-- Los permisos de columna impiden leer códigos estáticos o cambiar el rol/Auth.
do $$ declare t text; columnas text; begin
  foreach t in array array['personas','membresias','servicios','reservas','invitaciones','permisos_laborales','credenciales','eventos_acceso'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated',t);
    select string_agg(quote_ident(attname),',') into columnas from pg_attribute
      where attrelid=format('public.%I',t)::regclass and attnum>0 and not attisdropped;
    execute format('revoke select(%s),insert(%s),update(%s),references(%s) on public.%I from public,anon,authenticated',columnas,columnas,columnas,columnas,t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
grant select(id,nombre,categoria,grupo_facial,tipo_credencial,activo,created_at,auth_user_id,email,telefono,tipo_documento,numero_documento,cargo) on public.personas to authenticated;
grant select on public.membresias,public.servicios,public.reservas,public.invitaciones,public.permisos_laborales,public.eventos_acceso to authenticated;
grant insert(persona_id,servicio_id,fecha_inicio,fecha_fin,estado) on public.reservas to authenticated;
grant update(servicio_id,fecha_inicio,fecha_fin,estado) on public.reservas to authenticated;
grant update(estado) on public.invitaciones,public.permisos_laborales to authenticated;

-- Una política restrictiva conserva el límite aunque existan políticas permisivas previas.
do $$ declare t text; rule text; begin
  foreach t in array array['personas','membresias','servicios','reservas','invitaciones','permisos_laborales','credenciales','eventos_acceso'] loop
    rule:=case t
      when 'personas' then 'id=(select private.nclub_persona_id()) or (select private.nclub_es_admin())'
      when 'membresias' then 'persona_id=(select private.nclub_persona_id()) or (select private.nclub_es_admin())'
      when 'reservas' then 'persona_id=(select private.nclub_persona_id()) or (select private.nclub_es_admin())'
      when 'eventos_acceso' then 'persona_id=(select private.nclub_persona_id()) or (select private.nclub_es_admin())'
      when 'servicios' then '(select private.nclub_persona_id()) is not null and (activo or (select private.nclub_es_admin()))'
      else '(select private.nclub_es_admin())' end;
    execute format('drop policy if exists nclub_lectura on public.%I',t);
    execute format('drop policy if exists nclub_limite_lectura on public.%I',t);
    execute format('create policy nclub_lectura on public.%I for select to authenticated using (true)',t);
    execute format('create policy nclub_limite_lectura on public.%I as restrictive for select to authenticated using (%s)',t,rule);
    -- Toda escritura está cerrada salvo los casos explícitos siguientes.
    execute format('drop policy if exists nclub_limite_insertar on public.%I',t);
    execute format('drop policy if exists nclub_limite_actualizar on public.%I',t);
    execute format('drop policy if exists nclub_limite_eliminar on public.%I',t);
    execute format('create policy nclub_limite_insertar on public.%I as restrictive for insert to authenticated with check (%s)',t,
      case when t='reservas' then 'persona_id=(select private.nclub_persona_id())' else 'false' end);
    rule:=case when t='reservas' then 'persona_id=(select private.nclub_persona_id()) or (select private.nclub_es_admin())'
      when t in ('invitaciones','permisos_laborales') then '(select private.nclub_es_admin())' else 'false' end;
    execute format('create policy nclub_limite_actualizar on public.%I as restrictive for update to authenticated using (%s) with check (%s)',t,rule,rule);
    execute format('create policy nclub_limite_eliminar on public.%I as restrictive for delete to authenticated using (false)',t);
  end loop;
end $$;
drop policy if exists nclub_reservar on public.reservas;
create policy nclub_reservar on public.reservas for insert to authenticated with check (persona_id=(select private.nclub_persona_id()));
drop policy if exists nclub_modificar_reserva on public.reservas;
create policy nclub_modificar_reserva on public.reservas for update to authenticated using (persona_id=(select private.nclub_persona_id()) or (select private.nclub_es_admin()));
drop policy if exists nclub_revocar on public.invitaciones;
create policy nclub_revocar on public.invitaciones for update to authenticated using ((select private.nclub_es_admin()));
drop policy if exists nclub_revocar on public.permisos_laborales;
create policy nclub_revocar on public.permisos_laborales for update to authenticated using ((select private.nclub_es_admin()));

create or replace function private.nclub_validar_membresia() returns trigger
language plpgsql security definer set search_path='' as $$
begin
  if not exists(select 1 from public.personas where id=new.persona_id and categoria=new.nivel and categoria in ('VIP','REGULAR')) then
    raise exception 'La membresía debe coincidir con la categoría de la persona.';
  end if;
  return new;
end $$;
drop trigger if exists nclub_validar_membresia on public.membresias;
create trigger nclub_validar_membresia before insert or update on public.membresias for each row execute function private.nclub_validar_membresia();

create or replace function private.nclub_validar_reserva() returns trigger
language plpgsql security definer set search_path='' as $$
declare s public.servicios; p public.personas; inicio timestamp; fin timestamp;
begin
  if tg_op='UPDATE' then
    if (new.id,new.persona_id,new.created_at) is distinct from (old.id,old.persona_id,old.created_at) then raise exception 'No puede cambiar el titular ni el identificador.'; end if;
    if old.estado='CANCELADA' then raise exception 'Una reserva cancelada no se puede modificar.'; end if;
    if new.estado='CANCELADA' then
      if (new.servicio_id,new.fecha_inicio,new.fecha_fin,new.actividad,new.destino) is distinct from (old.servicio_id,old.fecha_inicio,old.fecha_fin,old.actividad,old.destino) then raise exception 'Cancele sin modificar el horario.'; end if;
      return new;
    end if;
    if private.nclub_es_admin() and new.persona_id is distinct from private.nclub_persona_id() then raise exception 'Administración solo puede cancelar reservas ajenas.'; end if;
  elsif new.estado<>'CONFIRMADA' then raise exception 'Estado de reserva no válido.';
  end if;
  select * into s from public.servicios where id=new.servicio_id;
  select * into p from public.personas where id=new.persona_id;
  if not private.nclub_miembro_vigente(new.persona_id) then raise exception 'Se requiere una membresía vigente.'; end if;
  if s.id is null or not s.activo or (s.exclusivo_vip and p.categoria<>'VIP') then raise exception 'Tu membresía no incluye este servicio.'; end if;
  inicio:=new.fecha_inicio at time zone 'America/Bogota'; fin:=new.fecha_fin at time zone 'America/Bogota';
  if new.fecha_inicio<=now() or inicio::date>(now() at time zone 'America/Bogota')::date+90 then raise exception 'Elige una fecha futura dentro de 90 días.'; end if;
  if inicio::time<'08:00'::time or fin::time>'18:00'::time or fin::date<>inicio::date or extract(minute from inicio)<>0 or extract(second from inicio)<>0 or new.fecha_fin<>new.fecha_inicio+interval '1 hour' then raise exception 'Reserva bloques de una hora entre 08:00 y 18:00, hora Colombia.'; end if;
  if not exists(select 1 from public.membresias where persona_id=new.persona_id and vigencia_hasta>=new.fecha_fin) then raise exception 'La membresía no cubre la fecha de la reserva.'; end if;
  new.actividad:=s.nombre; new.destino:=s.destino;
  return new;
end $$;
drop trigger if exists nclub_validar_reserva on public.reservas;
create trigger nclub_validar_reserva before insert or update on public.reservas for each row execute function private.nclub_validar_reserva();

create or replace function private.nclub_validar_permiso() returns trigger
language plpgsql security definer set search_path='' as $$
declare categoria_persona text;
begin
  select categoria into categoria_persona from public.personas where id=new.persona_id;
  if tg_table_name='invitaciones' then
    if categoria_persona is distinct from 'INVITADO' then raise exception 'La persona debe ser un invitado.'; end if;
    -- Cancelar un registro antiguo siempre es posible, aunque el anfitrión haya vencido.
    if tg_op='UPDATE' and new.estado in ('CANCELADA','UTILIZADA') then return new; end if;
    if not private.nclub_miembro_vigente(new.anfitrion_id) then raise exception 'El anfitrión debe ser un miembro vigente e identificado.'; end if;
    if new.destino not in ('Restaurante principal','Recepción de golf') then raise exception 'Destino no permitido para invitados.'; end if;
    select nombre into new.anfitrion from public.personas where id=new.anfitrion_id;
  else
    if categoria_persona is distinct from new.tipo then raise exception 'El permiso no coincide con la categoría de la persona.'; end if;
    if tg_op='UPDATE' and new.estado='CANCELADO' then return new; end if;
    if (new.tipo='PERSONAL_INTERNO' and new.destino not in ('Cocina','Recepción','Operación de golf','Oficina administrativa'))
      or (new.tipo='TRABAJADOR_EXTERNO' and new.destino not in ('Mantenimiento','Entrada de servicio','Zona técnica')) then raise exception 'Zona laboral no permitida.'; end if;
  end if;
  return new;
end $$;
drop trigger if exists nclub_validar_invitacion on public.invitaciones;
create trigger nclub_validar_invitacion before insert or update on public.invitaciones for each row execute function private.nclub_validar_permiso();
drop trigger if exists nclub_validar_permiso on public.permisos_laborales;
create trigger nclub_validar_permiso before insert or update on public.permisos_laborales for each row execute function private.nclub_validar_permiso();

create or replace function public.consultar_disponibilidad(p_servicio text,p_fecha date)
returns table(start_time time,end_time time)
language plpgsql stable security definer set search_path='' as $$
declare p public.personas; s public.servicios; desde timestamptz; hasta timestamptz;
begin
  select * into p from public.personas where id=private.nclub_persona_id();
  select * into s from public.servicios where id=p_servicio;
  if p.id is null or not (private.nclub_es_admin() or private.nclub_miembro_vigente(p.id)) or s.id is null or not s.activo or (s.exclusivo_vip and p.categoria not in ('VIP','ADMIN')) then raise exception 'No autorizado para consultar este servicio.'; end if;
  if p_fecha is null or p_fecha<(now() at time zone 'America/Bogota')::date or p_fecha>(now() at time zone 'America/Bogota')::date+90 then raise exception 'Fecha fuera de rango.'; end if;
  desde:=p_fecha::timestamp at time zone 'America/Bogota'; hasta:=(p_fecha+1)::timestamp at time zone 'America/Bogota';
  return query select
    case when r.fecha_inicio<desde then '00:00'::time else (r.fecha_inicio at time zone 'America/Bogota')::time end,
    case when r.fecha_fin>=hasta then '24:00'::time else (r.fecha_fin at time zone 'America/Bogota')::time end
  from public.reservas r where r.servicio_id=p_servicio and r.estado='CONFIRMADA' and r.fecha_inicio<hasta and r.fecha_fin>desde;
end $$;

create or replace function public.emitir_credencial(p_persona_id text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.personas; token text; vence timestamptz; clase text;
begin
  if auth.uid() is null or (p_persona_id is distinct from private.nclub_persona_id() and not private.nclub_es_admin()) then raise exception 'No autorizado para emitir esta credencial.'; end if;
  select * into p from public.personas where id=p_persona_id for update;
  if p.id is null or not p.activo then raise exception 'Persona inactiva.'; end if;
  if p.categoria in ('VIP','REGULAR') then
    if not private.nclub_miembro_vigente(p.id) then raise exception 'Membresía suspendida o vencida.'; end if;
    clase:='MIEMBRO'; select least(now()+interval '1 hour',vigencia_hasta) into vence from public.membresias where persona_id=p.id;
  elsif p.categoria='INVITADO' then
    clase:='INVITACION';
    select least(i.valido_hasta,greatest(i.valido_desde,now())+interval '24 hours',m.vigencia_hasta) into vence
    from public.invitaciones i join public.membresias m on m.persona_id=i.anfitrion_id
    where i.persona_id=p.id and i.estado='ACTIVA' and i.valido_hasta>now() and private.nclub_miembro_vigente(i.anfitrion_id)
      and i.destino in ('Restaurante principal','Recepción de golf')
      and m.vigencia_hasta>greatest(i.valido_desde,now())
    order by i.valido_hasta desc limit 1;
  elsif p.categoria in ('PERSONAL_INTERNO','TRABAJADOR_EXTERNO') then
    clase:=case when p.categoria='PERSONAL_INTERNO' then 'TURNO' else 'ORDEN_EXTERNA' end;
    select least(valido_hasta,greatest(valido_desde,now())+interval '24 hours') into vence from public.permisos_laborales
    where persona_id=p.id and tipo=p.categoria and estado='ACTIVO' and valido_hasta>now()
      and ((tipo='PERSONAL_INTERNO' and destino in ('Cocina','Recepción','Operación de golf','Oficina administrativa'))
        or (tipo='TRABAJADOR_EXTERNO' and destino in ('Mantenimiento','Entrada de servicio','Zona técnica')))
    order by valido_hasta desc limit 1;
  else raise exception 'La cuenta administrativa no es una credencial de visitante.';
  end if;
  if vence is null or vence<=now() then raise exception 'No hay invitación, turno u orden vigente.'; end if;
  token:=encode(extensions.gen_random_bytes(32),'hex');
  update public.credenciales set revocada_en=now() where persona_id=p.id and revocada_en is null;
  insert into public.credenciales(persona_id,token_hash,tipo,expira_en) values(p.id,encode(extensions.digest(token,'sha256'),'hex'),clase,vence);
  return jsonb_build_object('token',token,'expires_at',vence);
end $$;

drop function if exists public.actualizar_persona(text,text,text);
drop function if exists public.actualizar_persona(text,text,text,text,text,text,text,timestamptz);
create or replace function public.actualizar_persona(
  p_id text,p_nombre text,p_estado text,p_email text,p_telefono text,
  p_tipo_documento text,p_numero_documento text,p_cargo text,p_vigencia_hasta timestamptz
) returns void
language plpgsql security definer set search_path='' as $$
declare p public.personas; documento text;
begin
  if not private.nclub_es_admin() then raise exception 'Solo administradores activos.'; end if;
  if (p_tipo_documento is null)<>(p_numero_documento is null) then raise exception 'Completa el tipo y numero de documento.'; end if;
  if p_tipo_documento is not null and p_tipo_documento not in ('CC','CE','PASAPORTE','OTRO') then raise exception 'Tipo de documento no valido.'; end if;
  documento:=case when p_numero_documento is null then null else regexp_replace(upper(trim(p_numero_documento)),'[^A-Z0-9]','','g') end;
  if documento is not null and length(documento) not between 5 and 30 then raise exception 'Numero de documento no valido.'; end if;
  if p_estado is null or p_estado not in ('active','inactive','suspended') or p_nombre is null or length(trim(p_nombre)) not between 3 and 100 then raise exception 'Nombre o estado no válido.'; end if;
  select * into p from public.personas where id=p_id for update;
  if p.id is null then raise exception 'Persona inexistente.'; end if;
  if p.id=private.nclub_persona_id() and p_estado<>'active' then raise exception 'No puedes desactivar tu propia cuenta administrativa.'; end if;
  update public.personas set nombre=trim(p_nombre),email=nullif(lower(trim(coalesce(p_email,''))),''),
    telefono=nullif(trim(coalesce(p_telefono,'')),''),tipo_documento=p_tipo_documento,numero_documento=documento,
    cargo=nullif(trim(coalesce(p_cargo,'')),''),activo=(p_estado='active' or (p_estado='suspended' and categoria in ('VIP','REGULAR'))) where id=p_id;
  if p.categoria in ('VIP','REGULAR') then
    update public.membresias set estado=case when p_estado='suspended' then 'SUSPENDIDA' else 'ACTIVA' end where persona_id=p_id;
    if p_vigencia_hasta is not null then update public.membresias set vigencia_hasta=p_vigencia_hasta where persona_id=p_id; end if;
    -- Activar una persona no renueva una membresía vencida.
  end if;
end $$;

drop function if exists public.crear_visitante(text,text,text,text,timestamptz,timestamptz,text);
create or replace function public.crear_visitante(
  p_nombre text,p_categoria text,p_anfitrion text,p_empresa text,p_desde timestamptz,p_hasta timestamptz,p_destino text,
  p_email text,p_telefono text,p_tipo_documento text,p_numero_documento text
) returns jsonb
language plpgsql security definer set search_path='' as $$
declare persona text; persona_categoria text; codigo text; resultado jsonb; documento text;
begin
  if not private.nclub_es_admin() then raise exception 'Solo administradores activos.'; end if;
  if p_tipo_documento is null or p_tipo_documento not in ('CC','CE','PASAPORTE','OTRO') or p_numero_documento is null then raise exception 'El documento de identidad es obligatorio.'; end if;
  documento:=regexp_replace(upper(trim(p_numero_documento)),'[^A-Z0-9]','','g');
  if length(documento) not between 5 and 30 then raise exception 'Numero de documento no valido.'; end if;
  if p_categoria is null or p_categoria not in ('INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO') then raise exception 'Categoría no válida para este formulario.'; end if;
  if p_nombre is null or length(trim(p_nombre)) not between 3 and 100 then raise exception 'Escribe un nombre válido.'; end if;
  if p_desde is null or p_hasta is null or p_desde>=p_hasta or p_hasta<=now() or p_hasta>p_desde+interval '7 days' then raise exception 'Vigencia no válida (máximo 7 días).'; end if;
  if p_categoria<>'INVITADO' and (p_empresa is null or length(trim(p_empresa)) not between 2 and 100) then raise exception 'Escribe una empresa válida.'; end if;
  perform pg_advisory_xact_lock(hashtextextended('nclub:documento:'||p_tipo_documento||':'||documento,0));
  select id,categoria into persona,persona_categoria from public.personas
    where tipo_documento=p_tipo_documento and numero_documento=documento for update;
  if persona is not null then
    if persona_categoria<>p_categoria then raise exception 'Ese documento ya esta registrado como otra categoria de persona.'; end if;
    if p_categoria='INVITADO' and exists(select 1 from public.invitaciones where persona_id=persona and estado='ACTIVA' and valido_hasta>now()) then
      raise exception 'Esta persona ya tiene una invitacion vigente.';
    end if;
    update public.invitaciones set estado='UTILIZADA' where persona_id=persona and estado='ACTIVA' and valido_hasta<=now();
    codigo:='AUT-'||gen_random_uuid()::text;
    update public.personas set nombre=trim(p_nombre),email=nullif(lower(trim(coalesce(p_email,''))),''),
      telefono=nullif(trim(coalesce(p_telefono,'')),''),cargo=nullif(trim(coalesce(p_empresa,'')),''),activo=true where id=persona;
  else
    persona:='PER-'||gen_random_uuid()::text; codigo:='AUT-'||gen_random_uuid()::text;
    insert into public.personas(id,nombre,categoria,grupo_facial,tipo_credencial,codigo_credencial,cargo,email,telefono,tipo_documento,numero_documento)
    values(persona,trim(p_nombre),p_categoria,'non_member',case when p_categoria='PERSONAL_INTERNO' then 'CARNET' else 'QR' end,codigo,
      nullif(trim(coalesce(p_empresa,'')),''),nullif(lower(trim(coalesce(p_email,''))),''),nullif(trim(coalesce(p_telefono,'')),''),p_tipo_documento,documento);
  end if;
  if p_categoria='INVITADO' then
    insert into public.invitaciones(codigo_qr,persona_id,anfitrion,anfitrion_id,destino,valido_desde,valido_hasta)
    values(codigo,persona,'Por confirmar',p_anfitrion,p_destino,p_desde,p_hasta);
  else
    insert into public.permisos_laborales(codigo_autorizacion,persona_id,tipo,actividad,empresa,destino,valido_desde,valido_hasta,requiere_acompanamiento)
    values(codigo,persona,p_categoria,case when p_categoria='PERSONAL_INTERNO' then 'Turno de personal' else 'Orden de trabajo' end,trim(p_empresa),p_destino,p_desde,p_hasta,p_categoria='TRABAJADOR_EXTERNO');
  end if;
  resultado:=public.emitir_credencial(persona);
  return resultado||jsonb_build_object('user_id',persona);
end $$;

revoke all on function public.consultar_disponibilidad(text,date),public.emitir_credencial(text),public.actualizar_persona(text,text,text,text,text,text,text,text,timestamptz),public.crear_visitante(text,text,text,text,timestamptz,timestamptz,text,text,text,text,text) from public,anon;
grant execute on function public.consultar_disponibilidad(text,date),public.emitir_credencial(text),public.actualizar_persona(text,text,text,text,text,text,text,text,timestamptz),public.crear_visitante(text,text,text,text,timestamptz,timestamptz,text,text,text,text,text) to authenticated;
revoke all on function private.nclub_validar_membresia(),private.nclub_validar_reserva(),private.nclub_validar_permiso() from public,anon,authenticated;

-- Publicación opcional: el polling de la app sigue funcionando si no existe.
do $$ declare t text; begin
  if exists(select 1 from pg_publication where pubname='supabase_realtime') then
    foreach t in array array['personas','membresias','servicios','reservas','invitaciones','permisos_laborales','eventos_acceso'] loop
      if not exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename=t) then
        execute format('alter publication supabase_realtime add table public.%I',t);
      end if;
    end loop;
  end if;
end $$;
notify pgrst, 'reload schema';
commit;
