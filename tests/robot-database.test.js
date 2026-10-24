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
const ADMIN = "20000000-0000-4000-8000-000000000001";
const MEMBER = "20000000-0000-4000-8000-000000000002";

test("robot reception schema: service writes, ADMIN reads, members and visitors see nothing", async (t) => {
  const db = new PGlite({ extensions: { btree_gist, pgcrypto } });
  try {
    await db.exec(bootstrap);
    await db.exec(await sql("../supabase/nclub_completo.sql"));
    await db.exec(await sql("../supabase/datos_demo.sql"));
    const robot = await sql("../supabase/recepcion_robot.sql");
    await db.exec(robot);
    await db.exec(robot); // idempotente
    await db.query("insert into auth.users(id) values($1),($2)", [ADMIN, MEMBER]);
    await db.query("update public.personas set auth_user_id=$1 where id='ADMIN001'", [ADMIN]);
    await db.query("update public.personas set auth_user_id=$1 where id='REG001'", [MEMBER]);
    const as = async (role, sub = "") =>
      db.exec(`reset role; set request.jwt.claim.sub='${sub}'; set role ${role};`);

    await t.test("backend (service_role) records a full session", async () => {
      await as("service_role");
      const { rows } = await db.query(
        "insert into public.sesiones_atencion(robot_id,simulacion) values('robot1',true) returning id",
      );
      const id = rows[0].id;
      await db.query(
        "insert into public.eventos_identificacion(sesion_id,tipo,resultado,persona_candidata,similitud,umbral) values($1,'ROSTRO','COINCIDE','VIP001',0.78,0.62)",
        [id],
      );
      await db.query(
        "insert into public.transcripciones(sesion_id,robot_id,texto,intencion) values($1,'robot1','Buenos días','SALUDO')",
        [id],
      );
      await db.query(
        `update public.sesiones_atencion set persona_id='VIP001',categoria_detectada='VIP',categoria_confirmada='VIP',
         decision='AUTORIZADO',metodo_verificacion=array['facial','credencial NFC'],destino='VIP Lounge' where id=$1`,
        [id],
      );
      await db.query(
        "insert into public.auditoria(actor,accion,entidad,entidad_id) values('robot:robot1','decision','persona','VIP001')",
      );
      assert.equal((await db.query("select count(*)::int n from public.robots")).rows[0].n, 2);
    });

    await t.test("an authorized decision requires a confirmed identity", async () => {
      await as("service_role");
      await assert.rejects(
        db.exec("insert into public.sesiones_atencion(robot_id,decision) values('robot1','AUTORIZADO')"),
        /check/,
      );
    });

    await t.test("audit log is append-only even for the server", async () => {
      await as("service_role");
      await assert.rejects(db.exec("delete from public.auditoria"), /auditoría/);
      await assert.rejects(db.exec("update public.auditoria set actor='x'"), /auditoría/);
    });

    await t.test("ADMIN reads sessions, transcripts and identification events", async () => {
      await as("authenticated", ADMIN);
      assert.equal((await db.query("select * from public.sesiones_atencion")).rows.length, 1);
      assert.equal((await db.query("select * from public.transcripciones")).rows.length, 1);
      assert.equal((await db.query("select * from public.eventos_identificacion")).rows.length, 1);
      await assert.rejects(
        db.exec("insert into public.transcripciones(sesion_id,robot_id,texto) select id,'robot1','falso' from public.sesiones_atencion"),
        /permission denied/,
      );
      await assert.rejects(db.exec("select * from public.rutas_compartidas"), /permission denied/);
    });

    await t.test("members and anonymous users cannot read robot data", async () => {
      await as("authenticated", MEMBER);
      for (const table of ["robots", "sesiones_atencion", "transcripciones", "eventos_identificacion", "evidencias", "auditoria"])
        assert.equal((await db.query(`select * from public.${table}`)).rows.length, 0, table);
      await as("anon");
      await assert.rejects(db.exec("select * from public.sesiones_atencion"), /permission denied/);
    });
  } finally {
    await db.close();
  }
});
