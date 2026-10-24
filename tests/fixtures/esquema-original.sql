-- Copia de las cinco tablas y registros compartidos por el usuario.
-- Se omite únicamente el segundo CREATE/INSERT de personas, que estaba duplicado.
create table public.personas (
 id text primary key, nombre text not null,
 categoria text not null check(categoria in ('VIP','REGULAR','INVITADO','PERSONAL_INTERNO','TRABAJADOR_EXTERNO')),
 grupo_facial text not null check(grupo_facial in ('member','non_member')),
 tipo_credencial text not null, codigo_credencial text not null unique,
 activo boolean not null default true, created_at timestamptz default now()
);
create table public.membresias (
 persona_id text primary key references public.personas(id),
 nivel text not null check(nivel in ('VIP','REGULAR')),
 estado text not null default 'ACTIVA' check(estado in ('ACTIVA','SUSPENDIDA')),
 vigencia_hasta timestamptz not null
);
create table public.reservas (
 id text primary key, persona_id text not null references public.personas(id),
 actividad text not null, destino text not null,
 fecha_inicio timestamptz not null, fecha_fin timestamptz not null,
 estado text not null default 'CONFIRMADA' check(estado in ('CONFIRMADA','CANCELADA')),
 check(fecha_fin>fecha_inicio)
);
create table public.invitaciones (
 codigo_qr text primary key, persona_id text not null references public.personas(id),
 anfitrion text not null, destino text not null,
 valido_desde timestamptz not null, valido_hasta timestamptz not null,
 estado text not null default 'ACTIVA' check(estado in ('ACTIVA','CANCELADA','UTILIZADA')),
 check(valido_hasta>valido_desde)
);
create table public.permisos_laborales (
 codigo_autorizacion text primary key, persona_id text not null references public.personas(id),
 tipo text not null check(tipo in ('PERSONAL_INTERNO','TRABAJADOR_EXTERNO')),
 actividad text not null, destino text not null,
 valido_desde timestamptz not null, valido_hasta timestamptz not null,
 requiere_acompanamiento boolean not null default false,
 estado text not null default 'ACTIVO' check(estado in ('ACTIVO','CANCELADO')),
 check(valido_hasta>valido_desde)
);
alter table public.personas enable row level security;
alter table public.membresias enable row level security;
alter table public.reservas enable row level security;
alter table public.invitaciones enable row level security;
alter table public.permisos_laborales enable row level security;
insert into public.personas(id,nombre,categoria,grupo_facial,tipo_credencial,codigo_credencial) values
('VIP001','Valeria Torres','VIP','member','NFC','NFC-VIP-001'),
('REG001','Santiago Ruiz','REGULAR','member','APP','APP-REG-001'),
('INV001','Camila López','INVITADO','non_member','QR','QR-INV-001'),
('EMP001','Daniel Moreno','PERSONAL_INTERNO','non_member','CARNET','CAR-EMP-001'),
('EXT001','Laura Pérez','TRABAJADOR_EXTERNO','non_member','QR','QR-EXT-001');
insert into public.membresias values
('VIP001','VIP','ACTIVA',now()+interval '180 days'),('REG001','REGULAR','ACTIVA',now()+interval '180 days');
insert into public.reservas(id,persona_id,actividad,destino,fecha_inicio,fecha_fin) values
('RES001','VIP001','Acceso a zona VIP','VIP Lounge',now()-interval '1 hour',now()+interval '8 hours'),
('RES002','REG001','Reserva de golf','Campo de golf',now()-interval '1 hour',now()+interval '8 hours');
insert into public.invitaciones(codigo_qr,persona_id,anfitrion,destino,valido_desde,valido_hasta) values
('QR-INV-001','INV001','Valeria Torres','Restaurante principal',now()-interval '1 hour',now()+interval '8 hours');
insert into public.permisos_laborales(codigo_autorizacion,persona_id,tipo,actividad,destino,valido_desde,valido_hasta,requiere_acompanamiento) values
('CAR-EMP-001','EMP001','PERSONAL_INTERNO','Turno administrativo','Oficina administrativa',now()-interval '1 hour',now()+interval '8 hours',false),
('QR-EXT-001','EXT001','TRABAJADOR_EXTERNO','Mantenimiento eléctrico','Zona técnica',now()-interval '1 hour',now()+interval '8 hours',true);
