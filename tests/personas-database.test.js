import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { PGlite } from "@electric-sql/pglite";
import { btree_gist } from "@electric-sql/pglite/contrib/btree_gist";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const sql = (name) => readFile(new URL(name, import.meta.url), "utf8");
const bootstrap = `create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth; create table auth.users(id uuid primary key);
  create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
  grant usage on schema auth to authenticated;
  grant execute on function auth.uid() to authenticated;
  create publication supabase_realtime;`;
const ids = {
  VIP001: "10000000-0000-4000-8000-000000000001",
  REG001: "10000000-0000-4000-8000-000000000002",
  INV001: "10000000-0000-4000-8000-000000000003",
  EMP001: "10000000-0000-4000-8000-000000000004",
  EXT001: "10000000-0000-4000-8000-000000000005",
  ADMIN001: "10000000-0000-4000-8000-000000000006",
};
const localTime = (time) => `(((now() at time zone 'America/Bogota')::date+4+time '${time}') at time zone 'America/Bogota')`;

test("Spanish SQL upgrades the supplied tables and enforces real access boundaries", async (t) => {
  const db = new PGlite({ extensions: { btree_gist, pgcrypto } });
  const install = await sql("../supabase/nclub_completo.sql");
  try {
    await db.exec(bootstrap);
    await db.exec(await sql("./fixtures/esquema-original.sql"));
    const original = (await db.query("select id,nombre,categoria,codigo_credencial from public.personas order by id")).rows;
    const oldBookings = (await db.query("select id,fecha_inicio,fecha_fin from public.reservas order by id")).rows;
    // A permissive policy or old column grant must not defeat the new boundary.
    await db.exec("create policy old_allow_all on public.personas for all to authenticated using(true) with check(true); grant update(categoria) on public.personas to authenticated");
    await db.exec(install);
    await db.exec(await sql("../supabase/datos_demo.sql"));
    await db.exec(install);
    await db.exec(await sql("../supabase/datos_demo.sql"));
    for (const [persona, auth] of Object.entries(ids)) {
      await db.query("insert into auth.users(id) values($1)", [auth]);
      await db.query("update public.personas set auth_user_id=$1 where id=$2", [auth, persona]);
    }
    const login = async (persona) => {
      await db.exec(`reset role; set request.jwt.claim.sub='${ids[persona]}'; set role authenticated;`);
    };
    await t.test("repeating installation preserves original identities, codes and reservation windows", async () => {
      assert.deepEqual((await db.query("select id,nombre,categoria,codigo_credencial from public.personas where id<>'ADMIN001' order by id")).rows, original);
      assert.deepEqual((await db.query("select id,fecha_inicio,fecha_fin from public.reservas where id in ('RES001','RES002') order by id")).rows, oldBookings);
      assert.equal((await db.query("select count(*) from public.personas")).rows[0].count, 6);
      assert.equal((await db.query("select anfitrion_id from public.invitaciones where codigo_qr='QR-INV-001'")).rows[0].anfitrion_id, "VIP001");
      assert.equal((await db.query("select servicio_id from public.reservas where id='RES001'")).rows[0].servicio_id, "lounge");
    });
    await t.test("member reads own rows and cannot read static codes or promote their account", async () => {
      await login("REG001");
      assert.deepEqual((await db.query("select id from public.personas")).rows, [{ id: "REG001" }]);
      assert.equal((await db.query("select * from public.membresias")).rows.length, 1);
      assert.ok((await db.query("select * from public.reservas")).rows.every((r) => r.persona_id === "REG001"));
      await assert.rejects(db.exec("select codigo_credencial from public.personas"), /permission denied/);
      await assert.rejects(db.exec("update public.personas set categoria='ADMIN' where id='REG001'"), /permission denied/);
      await assert.rejects(db.exec("update public.personas set auth_user_id=null where id='REG001'"), /permission denied/);
      await assert.rejects(db.exec("update public.membresias set vigencia_hasta=now()+interval '100 years'"), /permission denied/);
      await assert.rejects(db.exec("select token_hash from public.credenciales"), /permission denied/);
    });
    await t.test("guests, staff and contractors stay outside the app even with an Auth association", async () => {
      for (const persona of ["INV001", "EMP001", "EXT001"]) {
        await login(persona);
        assert.equal((await db.query("select id from public.personas")).rows.length, 0);
        for (const table of ["membresias", "servicios", "reservas", "invitaciones", "permisos_laborales", "eventos_acceso"])
          assert.equal((await db.query(`select * from public.${table}`)).rows.length, 0);
        await assert.rejects(db.exec(`select public.emitir_credencial('${persona}')`), /No autorizado/);
        await assert.rejects(db.exec("select * from public.consultar_disponibilidad('golf-1',(now() at time zone 'America/Bogota')::date+1)"), /No autorizado/);
      }
    });
    await t.test("VIP restriction, allowed time and membership expiry are validated on the server", async () => {
      await login("REG001");
      await assert.rejects(db.exec(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('REG001','lounge',${localTime("11:00")},${localTime("12:00")})`), /no incluye/);
      await assert.rejects(db.exec(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('REG001','golf-3',${localTime("07:00")},${localTime("08:00")})`), /una hora/);
      await db.exec("reset role; update public.membresias set vigencia_hasta=now()-interval '1 second' where persona_id='REG001'");
      await login("REG001");
      await assert.rejects(db.exec("select public.emitir_credencial('REG001')"), /vencida/);
      await assert.rejects(db.exec(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('REG001','golf-3',${localTime("11:00")},${localTime("12:00")})`), /vigente/);
      await db.exec("reset role; update public.membresias set vigencia_hasta=now()+interval '180 days' where persona_id='REG001'");
    });
    await t.test("resource and personal overlap are atomic; cancellation frees the slot", async () => {
      await login("REG001");
      const booking = (await db.query(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('REG001','golf-3',${localTime("11:00")},${localTime("12:00")}) returning id,actividad,destino`)).rows[0];
      assert.equal(booking.actividad, "Campo de golf · Cancha 3");
      await assert.rejects(db.exec(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('REG001','golf-4',${localTime("11:00")},${localTime("12:00")})`), /exclusion/);
      await login("VIP001");
      await assert.rejects(db.exec(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('VIP001','golf-3',${localTime("11:00")},${localTime("12:00")})`), /exclusion/);
      const availability = (await db.query("select * from public.consultar_disponibilidad('golf-3',(now() at time zone 'America/Bogota')::date+4)")).rows;
      assert.deepEqual(Object.keys(availability[0]).sort(), ["end_time", "start_time"]);
      await db.query("update public.reservas set estado='CANCELADA' where id=$1", [booking.id]);
      assert.equal((await db.query("select estado from public.reservas where id=$1", [booking.id])).rows.length, 0);
      await login("REG001");
      await db.query("update public.reservas set estado='CANCELADA' where id=$1", [booking.id]);
      await login("VIP001");
      await db.exec(`insert into public.reservas(persona_id,servicio_id,fecha_inicio,fecha_fin) values('VIP001','golf-3',${localTime("11:00")},${localTime("12:00")})`);
    });
    await t.test("original nine-hour reservations can be cancelled without rewriting their dates", async () => {
      await login("REG001");
      const result = await db.query("update public.reservas set estado='CANCELADA' where id='RES002' returning id");
      assert.equal(result.rows[0].id, "RES002");
    });
    await t.test("tokens are random, hashed, rotated and bounded by membership validity", async () => {
      await login("REG001");
      const first = (await db.query("select public.emitir_credencial('REG001') as credential")).rows[0].credential;
      const second = (await db.query("select public.emitir_credencial('REG001') as credential")).rows[0].credential;
      assert.match(first.token, /^[a-f0-9]{64}$/);
      assert.notEqual(first.token, second.token);
      await assert.rejects(db.exec("select public.emitir_credencial('VIP001')"), /No autorizado/);
      await db.exec("reset role");
      const hashes = (await db.query("select token_hash,revocada_en from public.credenciales where persona_id='REG001'")).rows;
      assert.equal(hashes.filter((r) => r.revocada_en).length, 1);
      assert.ok(hashes.every((r) => ![first.token, second.token].includes(r.token_hash)));
    });
    await t.test("admin manages all visitors; revoked permission prevents new credentials", async () => {
      await login("ADMIN001");
      assert.equal((await db.query("select id from public.personas")).rows.length, 6);
      for (const persona of ["INV001", "EMP001", "EXT001"])
        assert.match((await db.query(`select public.emitir_credencial('${persona}') as credential`)).rows[0].credential.token, /^[a-f0-9]{64}$/);
      await db.exec("update public.permisos_laborales set estado='CANCELADO' where persona_id='EXT001'");
      await assert.rejects(db.exec("select public.emitir_credencial('EXT001')"), /vigente/);
      await db.exec("select public.actualizar_persona('REG001','Santiago Ruiz','suspended')");
      await assert.rejects(db.exec("select public.emitir_credencial('REG001')"), /suspendida/);
      await db.exec("select public.actualizar_persona('REG001','Santiago Ruiz','active')");
    });
    await t.test("admin visitor creation is atomic, has no app account, enforces zone and escort", async () => {
      await login("ADMIN001");
      const guest = (await db.query("select public.crear_visitante('Invitado nuevo','INVITADO','VIP001',null,now()+interval '3 days',now()+interval '3 days 2 hours','Restaurante principal') as visitor")).rows[0].visitor;
      assert.ok(new Date(guest.expires_at).getTime() > Date.now() + 3 * 86400000);
      assert.equal((await db.query("select auth_user_id from public.personas where id=$1", [guest.user_id])).rows[0].auth_user_id, null);
      const before = (await db.query("select count(*) from public.personas")).rows[0].count;
      await assert.rejects(db.exec("select public.crear_visitante('Proveedor malo','TRABAJADOR_EXTERNO',null,'Empresa',now(),now()+interval '1 hour','VIP Lounge')"), /Zona laboral/);
      assert.equal((await db.query("select count(*) from public.personas")).rows[0].count, before);
      const worker = (await db.query("select public.crear_visitante('Proveedor nuevo','TRABAJADOR_EXTERNO',null,'Empresa',now(),now()+interval '1 hour','Zona técnica') as visitor")).rows[0].visitor;
      assert.equal((await db.query("select requiere_acompanamiento from public.permisos_laborales where persona_id=$1", [worker.user_id])).rows[0].requiere_acompanamiento, true);
      await assert.rejects(db.exec("select public.crear_visitante('Administrador falso','ADMIN',null,null,now(),now()+interval '1 hour','Recepción')"), /Categoría/);
      await login("REG001");
      await assert.rejects(db.exec("select public.crear_visitante('Invitado falso','INVITADO','VIP001',null,now(),now()+interval '1 hour','Restaurante principal')"), /administradores/);
    });
    await t.test("browser cannot write access decisions; anonymous reads are denied", async () => {
      await login("ADMIN001");
      await assert.rejects(db.exec("insert into public.eventos_acceso(persona_id,categoria,tipo_evento,estado_acceso,destino,robot,simulacion) values('VIP001','VIP','vip_handoff','AUTORIZADO','VIP Lounge','robot2',false)"), /permission denied/);
      await db.exec("reset role; set role anon");
      await assert.rejects(db.exec("select id from public.personas"), /permission denied/);
      await assert.rejects(db.exec("select public.emitir_credencial('VIP001')"), /permission denied/);
    });
  } finally {
    await db.close();
  }
});

test("Spanish SQL also installs in a fresh database", async () => {
  const db = new PGlite({ extensions: { btree_gist, pgcrypto } });
  try {
    await db.exec(bootstrap);
    await db.exec(await sql("../supabase/nclub_completo.sql"));
    await db.exec(await sql("../supabase/datos_demo.sql"));
    assert.equal((await db.query("select count(*) from public.personas")).rows[0].count, 6);
    assert.equal((await db.query("select count(*) from public.servicios")).rows[0].count, 7);
  } finally {
    await db.close();
  }
});
