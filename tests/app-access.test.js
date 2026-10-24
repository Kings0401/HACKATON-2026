import test from "node:test";
import assert from "node:assert/strict";
import { seed } from "../src/demo.js";
import {
  sessionState,
  loginDemo,
  restoreSession,
  loadData,
} from "../src/data.js";

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

test("demo sessions enforce the app access boundary", async (t) => {
  const previous = {
    localStorage: globalThis.localStorage,
    sessionStorage: globalThis.sessionStorage,
  };
  globalThis.localStorage = storage();
  globalThis.sessionStorage = storage();
  const data = seed();
  localStorage.setItem("nclub-demo-v1", JSON.stringify(data));
  try {
    await t.test("visitor identities cannot sign in or leave a session", () => {
      for (const role of ["guest", "staff", "external"]) {
        assert.throws(() => loginDemo(`demo-${role}`), /solo para miembros/);
        assert.equal(sessionStorage.getItem("nclub-demo-profile"), null);
        assert.equal(sessionState.profile, null);
      }
    });
    await t.test("old visitor sessions are discarded on restore", async () => {
      for (const role of ["guest", "staff", "external"]) {
        sessionStorage.setItem("nclub-demo-profile", `demo-${role}`);
        assert.equal(await restoreSession(), null);
        assert.equal(sessionStorage.getItem("nclub-demo-profile"), null);
        assert.equal(sessionState.profile, null);
      }
    });
    await t.test(
      "members and administrators can sign in and restore",
      async () => {
        for (const role of ["vip", "regular", "admin"]) {
          const p = loginDemo(`demo-${role}`);
          assert.equal((await restoreSession()).id, p.id);
          assert.ok((await loadData()).services.length > 0);
        }
      },
    );
    await t.test(
      "changing an account to a visitor clears its session",
      async () => {
        loginDemo("demo-regular");
        data.profiles.find((p) => p.id === "demo-regular").role = "GUEST";
        localStorage.setItem("nclub-demo-v1", JSON.stringify(data));
        await assert.rejects(loadData(), /solo para miembros/);
        assert.equal(sessionState.profile, null);
        assert.equal(sessionStorage.getItem("nclub-demo-profile"), null);
      },
    );
  } finally {
    sessionState.mode = "live";
    sessionState.profile = null;
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
});
