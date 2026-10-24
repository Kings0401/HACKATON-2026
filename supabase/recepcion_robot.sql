-- N CLUB: recepción robótica (robots, sesiones, identificación, voz, evidencias,
-- rutas compartidas y auditoría). Ejecutar DESPUÉS de nclub_completo.sql, como
-- propietario, en SQL Editor. Aditivo e idempotente: no borra ni modifica datos.
--
-- Escritura: solo FastAPI con credencial de servidor (service_role).
-- Lectura desde la app: solo ADMIN activo (private.nclub_es_admin()).
-- No se guardan video ni fotogramas continuos; las evidencias puntuales van al
-- bucket privado evidencias-recepcion y aquí solo quedan sus metadatos.
begin;
set local search_path = public, extensions;

create table if not exists public.robots (
  id text primary key check (id ~ '^[A-Za-z0-9_-]{1,40}$'),
  nombre text not null,
  modelo text,
  firmware text,
  sdk_version text,
  estado text not null default 'DESCONECTADO' check (estado in ('DESCONECTADO','CONECTADO','DEGRADADO')),
  camara_ok boolean not null default false,
  microfono_ok boolean not null default false,
  simulado boolean not null default false,
  ultimo_latido timestamptz,
  created_at timestamptz not null default now()
);

-- robot_id sin FK: una sesión puede abrirse antes de persistir el primer latido.
create table if not exists public.sesiones_atencion (
  id uuid primary key default gen_random_uuid(),
  robot_id text not null,
  estado text not null default 'ACTIVA' check (estado in ('ACTIVA','CERRADA','EXPIRADA')),
  iniciada_en timestamptz not null default now(),
  finalizada_en timestamptz,
  simulacion boolean not null default false,
  persona_id text references public.personas(id),
  categoria_detectada text check (categoria_detectada in ('VIP','REGULAR','INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO')),
  categoria_confirmada text check (categoria_confirmada in ('VIP','REGULAR','INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO')),
  metodo_verificacion text[] not null default '{}',
  decision text check (decision in ('AUTORIZADO','DENEGADO','REVISION','ACOMPANAMIENTO','PENDIENTE')),
  justificacion text,
  validaciones jsonb not null default '[]',
  destino text,
  credencial_enmascarada text check (length(credencial_enmascarada) <= 16),
  created_at timestamptz not null default now(),
  check (decision is distinct from 'AUTORIZADO' or (persona_id is not null and categoria_confirmada is not null))
);

-- persona_candidata sin FK: la galería del robot puede ir por delante de la base.
create table if not exists public.eventos_identificacion (
  id uuid primary key default gen_random_uuid(),
  sesion_id uuid not null references public.sesiones_atencion(id),
  tipo text not null check (tipo in ('ROSTRO','QR','CREDENCIAL','VOZ','MANUAL')),
  resultado text not null check (resultado in ('COINCIDE','NO_COINCIDE','DESCONOCIDO','LEIDO','INVALIDO')),
  persona_candidata text,
  similitud real check (similitud between -1 and 1),
  umbral real,
  detalle jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create table if not exists public.evidencias (
  id uuid primary key default gen_random_uuid(),
  sesion_id uuid not null references public.sesiones_atencion(id),
  tipo text not null check (tipo in ('IMAGEN','AUDIO')),
  bucket text not null default 'evidencias-recepcion',
  ruta text not null unique,
  mime text not null check (mime in ('image/jpeg','audio/wav')),
  bytes integer not null check (bytes between 1 and 2000000),
  sha256 text not null check (length(sha256) = 64),
  consentimiento boolean not null check (consentimiento),
  retener_hasta timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists public.transcripciones (
  id uuid primary key default gen_random_uuid(),
  sesion_id uuid not null references public.sesiones_atencion(id),
  robot_id text not null,
  texto text not null check (length(texto) <= 1000),
  idioma text not null default 'es-CO',
  confianza real,
  motor text,
  intencion text,
  inicio timestamptz,
  fin timestamptz,
  evidencia_id uuid references public.evidencias(id),
  created_at timestamptz not null default now()
);

-- Solo geometría de la ruta: sin nombres, identificadores ni permisos.
create table if not exists public.rutas_compartidas (
  token_hash text primary key check (length(token_hash) = 64),
  categoria text not null,
  destino text not null,
  ruta jsonb not null,
  expira_en timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists public.auditoria (
  id bigint generated always as identity primary key,
  actor text not null,
  accion text not null,
  entidad text not null,
  entidad_id text not null,
  detalle jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists sesiones_robot_fecha on public.sesiones_atencion(robot_id, created_at desc);
create index if not exists sesiones_persona on public.sesiones_atencion(persona_id);
create index if not exists sesiones_fecha on public.sesiones_atencion(created_at desc);
create index if not exists identificacion_sesion on public.eventos_identificacion(sesion_id);
create index if not exists evidencias_sesion on public.evidencias(sesion_id);
create index if not exists evidencias_retencion on public.evidencias(retener_hasta);
create index if not exists transcripciones_sesion on public.transcripciones(sesion_id);
create index if not exists transcripciones_evidencia on public.transcripciones(evidencia_id);
create index if not exists transcripciones_fecha on public.transcripciones(created_at desc);
create index if not exists rutas_expiracion on public.rutas_compartidas(expira_en);
create index if not exists auditoria_fecha on public.auditoria(created_at desc);

-- Auditoría de solo inserción, incluso para la credencial de servidor.
create or replace function private.nclub_auditoria_inmutable() returns trigger
language plpgsql set search_path='' as $$
begin
  raise exception 'La auditoría no se puede modificar ni borrar.';
end $$;
revoke all on function private.nclub_auditoria_inmutable() from public, anon, authenticated;
drop trigger if exists nclub_auditoria_inmutable on public.auditoria;
create trigger nclub_auditoria_inmutable before update or delete on public.auditoria
  for each row execute function private.nclub_auditoria_inmutable();

-- RLS: ADMIN lee; nadie escribe desde el navegador. Mismo patrón restrictivo
-- que nclub_completo.sql para resistir políticas permisivas previas.
do $$ declare t text; begin
  foreach t in array array['robots','sesiones_atencion','eventos_identificacion','evidencias','transcripciones','rutas_compartidas','auditoria'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated', t);
    execute format('grant all on public.%I to service_role', t);
    execute format('drop policy if exists nclub_lectura on public.%I', t);
    execute format('drop policy if exists nclub_limite_lectura on public.%I', t);
    execute format('drop policy if exists nclub_limite_insertar on public.%I', t);
    execute format('drop policy if exists nclub_limite_actualizar on public.%I', t);
    execute format('drop policy if exists nclub_limite_eliminar on public.%I', t);
    if t <> 'rutas_compartidas' then
      execute format('grant select on public.%I to authenticated', t);
      execute format('create policy nclub_lectura on public.%I for select to authenticated using ((select private.nclub_es_admin()))', t);
      execute format('create policy nclub_limite_lectura on public.%I as restrictive for select to authenticated using ((select private.nclub_es_admin()))', t);
    end if;
    -- Por comando: un FOR ALL restrictivo con false también bloquearía SELECT.
    execute format('create policy nclub_limite_insertar on public.%I as restrictive for insert to authenticated with check (false)', t);
    execute format('create policy nclub_limite_actualizar on public.%I as restrictive for update to authenticated using (false) with check (false)', t);
    execute format('create policy nclub_limite_eliminar on public.%I as restrictive for delete to authenticated using (false)', t);
  end loop;
end $$;

-- Bucket privado de evidencias (sin políticas para anon/authenticated: solo
-- FastAPI lo usa y entrega URL firmadas de corta duración a ADMIN).
do $$ begin
  if exists (select 1 from pg_namespace where nspname = 'storage') then
    insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
    values ('evidencias-recepcion', 'evidencias-recepcion', false, 2000000, array['image/jpeg','audio/wav'])
    on conflict (id) do nothing;
    insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
    values ('voces-nclub', 'voces-nclub', false, 8000000, array['audio/wav'])
    on conflict (id) do update set name=excluded.name, public=false,
      file_size_limit=excluded.file_size_limit, allowed_mime_types=excluded.allowed_mime_types;
  end if;
end $$;

-- Realtime privado: el backend emite broadcast al tema nclub:monitor y solo
-- ADMIN activo puede recibirlo. postgres_changes respeta las políticas RLS.
do $$ begin
  if exists (select 1 from pg_tables where schemaname = 'realtime' and tablename = 'messages') then
    execute 'drop policy if exists nclub_monitor_admin on realtime.messages';
    execute $p$create policy nclub_monitor_admin on realtime.messages for select to authenticated
      using ((select realtime.topic()) = 'nclub:monitor' and (select private.nclub_es_admin()))$p$;
  end if;
end $$;
do $$ declare t text; begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach t in array array['robots','sesiones_atencion','transcripciones','eventos_identificacion'] loop
      if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
        execute format('alter publication supabase_realtime add table public.%I', t);
      end if;
    end loop;
  end if;
end $$;

insert into public.robots(id, nombre, modelo)
values ('robot1', 'AGIBOT 01 · Recepción', 'AGIBOT X2 Ultra'),
       ('robot2', 'AGIBOT 02 · VIP Concierge', 'AGIBOT X2 Ultra')
on conflict (id) do nothing;

notify pgrst, 'reload schema';
commit;
