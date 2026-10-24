-- OPCIONAL. Ejecutar después de nclub_completo.sql para una demostración.
-- No sobrescribe ni reactiva registros existentes. No crea cuentas ni contraseñas.
begin;
insert into public.personas(id,nombre,categoria,grupo_facial,tipo_credencial,codigo_credencial) values
('VIP001','Valeria Torres','VIP','member','NFC','NFC-VIP-001'),
('REG001','Santiago Ruiz','REGULAR','member','APP','APP-REG-001'),
('INV001','Camila López','INVITADO','non_member','QR','QR-INV-001'),
('EMP001','Daniel Moreno','PERSONAL_INTERNO','non_member','CARNET','CAR-EMP-001'),
('EXT001','Laura Pérez','TRABAJADOR_EXTERNO','non_member','QR','QR-EXT-001'),
('ADMIN001','Administración N Club','ADMIN','non_member','CUENTA','ADMIN-001')
on conflict do nothing;
-- Documento demo del socio regular (el robot pregunta sus últimos cuatro dígitos); solo si está vacío.
update public.personas set tipo_documento='CC', numero_documento='1020304567'
where id='REG001' and numero_documento is null
  and not exists(select 1 from public.personas o where o.tipo_documento='CC' and o.numero_documento='1020304567');
insert into public.membresias(persona_id,nivel,estado,vigencia_hasta)
select * from (values
('VIP001','VIP','ACTIVA',now()+interval '180 days'),
('REG001','REGULAR','ACTIVA',now()+interval '180 days')) as d(persona_id,nivel,estado,vigencia_hasta)
where not exists(select 1 from public.membresias m where m.persona_id=d.persona_id)
on conflict do nothing;

-- Horarios futuros en Colombia; no se crean reservas de nueve horas ni pasadas.
insert into public.reservas(id,persona_id,servicio_id,actividad,destino,fecha_inicio,fecha_fin)
select * from (values
('DEMO-RES-VIP','VIP001','golf-2','Golf','Campo de golf · Cancha 2',
 ((now() at time zone 'America/Bogota')::date+1+time '16:00') at time zone 'America/Bogota',
 ((now() at time zone 'America/Bogota')::date+1+time '17:00') at time zone 'America/Bogota'),
('DEMO-RES-REG','REG001','golf-1','Golf','Campo de golf',
 ((now() at time zone 'America/Bogota')::date+1+time '10:00') at time zone 'America/Bogota',
 ((now() at time zone 'America/Bogota')::date+1+time '11:00') at time zone 'America/Bogota')) as d(id,persona_id,servicio_id,actividad,destino,fecha_inicio,fecha_fin)
where not exists(select 1 from public.reservas r where r.id=d.id)
  and exists(select 1 from public.personas p join public.membresias m on m.persona_id=p.id
    where p.id=d.persona_id and p.activo and p.categoria=m.nivel and m.estado='ACTIVA' and m.vigencia_hasta>=d.fecha_fin)
on conflict do nothing;
insert into public.invitaciones(codigo_qr,persona_id,anfitrion,anfitrion_id,destino,valido_desde,valido_hasta)
select 'QR-INV-001','INV001','Valeria Torres','VIP001','Restaurante principal',now()-interval '1 hour',now()+interval '8 hours'
where not exists(select 1 from public.invitaciones where codigo_qr='QR-INV-001')
  and private.nclub_miembro_vigente('VIP001') on conflict do nothing;
insert into public.permisos_laborales(codigo_autorizacion,persona_id,tipo,actividad,destino,valido_desde,valido_hasta,requiere_acompanamiento,empresa)
select * from (values
('CAR-EMP-001','EMP001','PERSONAL_INTERNO','Turno administrativo','Oficina administrativa',now()-interval '1 hour',now()+interval '8 hours',false,'N Club World'),
('QR-EXT-001','EXT001','TRABAJADOR_EXTERNO','Mantenimiento eléctrico','Zona técnica',now()-interval '1 hour',now()+interval '8 hours',true,'Proveedor de mantenimiento')) as d(codigo,persona_id,tipo,actividad,destino,desde,hasta,acompanamiento,empresa)
where not exists(select 1 from public.permisos_laborales p where p.codigo_autorizacion=d.codigo)
on conflict do nothing;
commit;
