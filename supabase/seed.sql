-- LEGADO: para el esquema en español usar datos_demo.sql, no este archivo.
-- Run AFTER 001_nclub.sql. Fictional identities; no passwords, no auth.users writes.
begin;
insert into public.profiles(id,full_name,email,role,public_id,position) values
('10000000-0000-4000-8000-000000000001','Gabriela Montenegro','gabriela@nclub.demo','VIP','NC-1001',null),
('10000000-0000-4000-8000-000000000002','Alejandro Ríos','alejandro@nclub.demo','REGULAR','NC-1002',null),
('10000000-0000-4000-8000-000000000003','Isabella Vargas','isabella@nclub.demo','GUEST','NC-1003',null),
('10000000-0000-4000-8000-000000000004','Camila Torres','camila@nclub.demo','STAFF','NC-1004','Hospitalidad y gastronomía'),
('10000000-0000-4000-8000-000000000005','Daniel Medina','daniel@nclub.demo','EXTERNAL','NC-1005','Técnico de mantenimiento'),
('10000000-0000-4000-8000-000000000006','Sofía Restrepo','sofia@nclub.demo','ADMIN','NC-1006','Administración')
on conflict (id) do nothing;
insert into public.services(id,name,description,category,vip_only,image)
select ('20000000-0000-4000-8000-'||lpad(n::text,12,'0'))::uuid,'Campo de golf · Cancha '||n,'Un recorrido entre naturaleza, tranquilidad y precisión.','golf',false,'/images/course.jpg' from generate_series(1,5)n on conflict (id) do nothing;
insert into public.services(id,name,description,category,vip_only,image) values
('20000000-0000-4000-8000-000000000006','Restaurante N Club','Sabores de temporada, momentos que permanecen.','restaurant',false,'/images/restaurant.jpg'),
('20000000-0000-4000-8000-000000000007','Lounge VIP','Un espacio reservado para lo extraordinario.','lounge',true,'/images/lounge.jpg') on conflict (id) do nothing;
insert into public.reservations(user_id,service_id,reservation_date,start_time,end_time) values
('10000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000002',(now() at time zone 'America/Bogota')::date+1,'16:00','17:00'),
('10000000-0000-4000-8000-000000000002','20000000-0000-4000-8000-000000000001',(now() at time zone 'America/Bogota')::date+1,'10:00','11:00') on conflict do nothing;
insert into public.invitations(guest_id,host_id,visit_date,valid_from,valid_until,destination)
select '10000000-0000-4000-8000-000000000003','10000000-0000-4000-8000-000000000001',(now() at time zone 'America/Bogota')::date,date_trunc('day',now() at time zone 'America/Bogota') at time zone 'America/Bogota',(date_trunc('day',now() at time zone 'America/Bogota')+interval '1 day') at time zone 'America/Bogota','RESTAURANT'
where not exists(select 1 from public.invitations where guest_id='10000000-0000-4000-8000-000000000003' and valid_until>now());
insert into public.work_assignments(worker_id,company,assignment_type,valid_from,valid_until,authorized_zone)
select worker_id::uuid,company,kind,now()-interval '1 hour',now()+interval '12 hours',zone from (values
('10000000-0000-4000-8000-000000000004','N Club World','SHIFT','KITCHEN'),
('10000000-0000-4000-8000-000000000005','Green Systems','EXTERNAL_ORDER','MAINTENANCE')) as x(worker_id,company,kind,zone)
where not exists(select 1 from public.work_assignments w where w.worker_id=x.worker_id::uuid and valid_until>now());
commit;
