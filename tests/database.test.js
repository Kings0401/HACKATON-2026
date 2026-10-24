import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { PGlite } from "@electric-sql/pglite";
import { btree_gist } from "@electric-sql/pglite/contrib/btree_gist";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

// Real PostgreSQL in WASM. Auth schema/JWT claims are emulated, not Supabase Auth.
test("migration, RLS, atomic availability, credentials and visitor permissions on PostgreSQL", async (t) => {
  const db = new PGlite({ extensions: { btree_gist, pgcrypto } });
  try {
    await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
      create schema auth; create table auth.users(id uuid primary key);
      create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
      grant usage on schema auth to authenticated; grant execute on function auth.uid() to authenticated;
      create publication supabase_realtime;`);
    await db.exec(
      await readFile(
        new URL("../supabase/migrations/001_nclub.sql", import.meta.url),
        "utf8",
      ),
    );
    await db.exec(
      await readFile(
        new URL("../supabase/migrations/002_app_access.sql", import.meta.url),
        "utf8",
      ),
    );
    await db.exec(
      await readFile(new URL("../supabase/seed.sql", import.meta.url), "utf8"),
    );
    const vip = "10000000-0000-4000-8000-000000000001",
      regular = "10000000-0000-4000-8000-000000000002",
      admin = "10000000-0000-4000-8000-000000000006";
    await db.exec(
      `insert into auth.users(id) select id from public.profiles where role in ('VIP','REGULAR','ADMIN'); update public.profiles set auth_user_id=id where role in ('VIP','REGULAR','ADMIN');`,
    );
    const login = async (id) => {
      await db.exec(
        `reset role; set request.jwt.claim.sub='${id}'; set role authenticated;`,
      );
    };
    await t.test(
      "visitor accounts cannot read app data or issue their own QR; admin still manages them",
      async () => {
        await db.exec("reset role");
        const visitors = (
          await db.query(
            "select id from public.profiles where role in ('GUEST','STAFF','EXTERNAL')",
          )
        ).rows;
        await db.exec(
          "insert into auth.users(id) select id from public.profiles where role in ('GUEST','STAFF','EXTERNAL'); update public.profiles set auth_user_id=id where role in ('GUEST','STAFF','EXTERNAL')",
        );
        for (const { id } of visitors) {
          await login(id);
          for (const table of [
            "profiles",
            "services",
            "reservations",
            "invitations",
            "work_assignments",
            "access_events",
          ])
            assert.equal(
              (await db.query(`select * from public.${table}`)).rows.length,
              0,
            );
          await assert.rejects(
            db.exec(`select public.issue_credential('${id}')`),
            /No autorizado/,
          );
          await assert.rejects(
            db.exec(
              `select * from public.get_availability('20000000-0000-4000-8000-000000000001',current_date+1)`,
            ),
            /No autorizado/,
          );
        }
        await login(admin);
        assert.equal(
          (
            await db.query(
              "select id from public.profiles where role in ('GUEST','STAFF','EXTERNAL')",
            )
          ).rows.length,
          3,
        );
        for (const { id } of visitors) {
          const result = (
            await db.query(
              `select public.issue_credential('${id}') as credential`,
            )
          ).rows[0].credential;
          assert.match(result.token, /^[a-f0-9]{64}$/);
        }
        await login(regular);
      },
    );
    await t.test(
      "regular reads only own profile and reservations",
      async () => {
        await login(regular);
        assert.equal(
          (await db.query("select * from public.profiles")).rows.length,
          1,
        );
        assert.equal(
          (await db.query("select * from public.reservations")).rows.length,
          1,
        );
      },
    );
    await t.test(
      "cannot promote own role or change auth association",
      async () => {
        await assert.rejects(
          db.exec(
            `update public.profiles set role='ADMIN' where id='${regular}'`,
          ),
          /permission denied/,
        );
        await assert.rejects(
          db.exec(`update public.profiles set auth_user_id='${vip}'`),
          /permission denied/,
        );
      },
    );
    await t.test(
      "regular cannot book VIP resource even through direct SQL",
      async () => {
        await assert.rejects(
          db.exec(
            `insert into public.reservations(user_id,service_id,reservation_date,start_time,end_time) values('${regular}','20000000-0000-4000-8000-000000000007',current_date+2,'11:00','12:00')`,
          ),
          /membresía no incluye/,
        );
      },
    );
    await t.test(
      "cannot forge access decisions or read credential hashes",
      async () => {
        await assert.rejects(
          db.exec(
            `insert into public.access_events(visitor_id,role,event_type,access_status,destination,robot_target,simulation) values('${regular}','VIP','vip_handoff','authorized','VIP_LOUNGE','robot2',false)`,
          ),
          /permission denied/,
        );
        await assert.rejects(
          db.exec("select token_hash from public.credentials"),
          /permission denied/,
        );
      },
    );
    await t.test(
      "availability exposes times, excludes member identities",
      async () => {
        const result = await db.query(
          `select * from public.get_availability('20000000-0000-4000-8000-000000000002',(now() at time zone 'America/Bogota')::date+1)`,
        );
        assert.deepEqual(Object.keys(result.rows[0]).sort(), [
          "end_time",
          "start_time",
        ]);
      },
    );
    await t.test("atomic resource overlap and own overlap fail", async () => {
      await assert.rejects(
        db.exec(
          `insert into public.reservations(user_id,service_id,reservation_date,start_time,end_time) values('${regular}','20000000-0000-4000-8000-000000000002',(now() at time zone 'America/Bogota')::date+1,'16:00','17:00')`,
        ),
        /exclusion/,
      );
      await assert.rejects(
        db.exec(
          `insert into public.reservations(user_id,service_id,reservation_date,start_time,end_time) values('${regular}','20000000-0000-4000-8000-000000000003',(now() at time zone 'America/Bogota')::date+1,'10:00','11:00')`,
        ),
        /exclusion/,
      );
    });
    await t.test("member cannot create admin invitation", async () => {
      await assert.rejects(
        db.exec(
          `select public.admin_create_visitor('Someone Test','GUEST','${vip}',null,now(),now()+interval '1 hour','RESTAURANT')`,
        ),
        /administradores/,
      );
    });
    await t.test(
      "credential token opaque, hash only, rotation revokes old",
      async () => {
        const a = (
          await db.query(
            `select public.issue_credential('${regular}') as credential`,
          )
        ).rows[0].credential;
        assert.match(a.token, /^[a-f0-9]{64}$/);
        assert.ok(a.expires_at);
        await assert.rejects(
          db.exec(`select public.issue_credential('${vip}')`),
          /No autorizado/,
        );
        const b = (
          await db.query(
            `select public.issue_credential('${regular}') as credential`,
          )
        ).rows[0].credential;
        assert.notEqual(a.token, b.token);
        await db.exec("reset role");
        const rows = (
          await db.query(
            `select token_hash,revoked_at from public.credentials where user_id='${regular}'`,
          )
        ).rows;
        assert.equal(rows.filter((r) => r.revoked_at).length, 1);
        assert.ok(
          rows.every(
            (r) => r.token_hash !== a.token && r.token_hash !== b.token,
          ),
        );
      },
    );
    await t.test(
      "admin can create a guest without Auth and expiry stays bounded",
      async () => {
        await login(admin);
        const result = (
          await db.query(
            `select public.admin_create_visitor('Guest Test','GUEST','${vip}',null,now(),now()+interval '30 minutes','RESTAURANT') as guest`,
          )
        ).rows[0].guest;
        assert.match(result.token, /^[a-f0-9]{64}$/);
        const guest = (
          await db.query(
            `select * from public.profiles where id='${result.user_id}'`,
          )
        ).rows[0];
        assert.equal(guest.auth_user_id, null);
        assert.equal(guest.role, "GUEST");
        assert.ok(
          new Date(result.expires_at).getTime() < Date.now() + 31 * 60000,
        );
      },
    );
    await t.test(
      "external social zones and arbitrary membership creation rejected atomically",
      async () => {
        const before = (await db.query("select count(*) from public.profiles"))
          .rows[0].count;
        await assert.rejects(
          db.exec(
            `select public.admin_create_visitor('Bad Contractor','EXTERNAL',null,'Company',now(),now()+interval '1 hour','RESTAURANT')`,
          ),
          /check constraint/,
        );
        await assert.rejects(
          db.exec(
            `select public.admin_create_visitor('Bad Admin','ADMIN',null,'Company',now(),now()+interval '1 hour','MAINTENANCE')`,
          ),
          /Categoría/,
        );
        assert.equal(
          (await db.query("select count(*) from public.profiles")).rows[0]
            .count,
          before,
        );
      },
    );
    await t.test(
      "QR issued in advance remains valid throughout future invitation window",
      async () => {
        const result = (
          await db.query(
            `select public.admin_create_visitor('Future Guest','GUEST','${vip}',null,now()+interval '3 days',now()+interval '3 days 2 hours','RESTAURANT') as guest`,
          )
        ).rows[0].guest;
        assert.ok(
          new Date(result.expires_at).getTime() > Date.now() + 3 * 86400000,
        );
      },
    );
    await t.test(
      "cancellation frees slot, regular cannot cancel someone else",
      async () => {
        await login(regular);
        const own = (await db.query("select id from public.reservations"))
          .rows[0].id;
        await db.exec(
          `update public.reservations set status='cancelled' where id='${own}'`,
        );
        const result = await db.query(
          `update public.reservations set status='cancelled' where user_id='${vip}' returning id`,
        );
        assert.equal(result.rows.length, 0);
        await db.exec(
          `insert into public.reservations(user_id,service_id,reservation_date,start_time,end_time) values('${regular}','20000000-0000-4000-8000-000000000001',(now() at time zone 'America/Bogota')::date+1,'10:00','11:00')`,
        );
      },
    );
  } finally {
    await db.close();
  }
});
