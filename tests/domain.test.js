import test from "node:test";
import assert from "node:assert/strict";
import { seed, evaluateDemo } from "../src/demo.js";
import {
  canBook,
  validateBooking,
  today,
  dateAfter,
  dateLabel,
  escape,
  canUseApp,
} from "../src/lib.js";
import { validateDecision } from "../src/api.js";

test("only members and administrators can use the app", () => {
  const d = seed();
  for (const p of d.profiles)
    assert.equal(canUseApp(p), ["VIP", "REGULAR", "ADMIN"].includes(p.role));
  for (const p of [null, undefined, {}, { role: "UNKNOWN" }])
    assert.equal(canUseApp(p), false);
});

test("regular cannot book VIP lounge; staff and external cannot book member services", () => {
  const d = seed(),
    lounge = d.services.find((s) => s.vip_only),
    golf = d.services[0];
  for (const role of ["REGULAR", "STAFF", "EXTERNAL", "GUEST"])
    assert.equal(
      canBook(
        d.profiles.find((p) => p.role === role),
        lounge,
      ),
      false,
    );
  for (const role of ["STAFF", "EXTERNAL", "GUEST"])
    assert.equal(
      canBook(
        d.profiles.find((p) => p.role === role),
        golf,
      ),
      false,
    );
  assert.equal(canBook(d.profiles[0], lounge), true);
  assert.equal(
    canBook({ ...d.profiles[0], membership_status: "suspended" }, golf),
    false,
  );
});
test("duplicate resource and conflicting personal reservations are rejected", () => {
  const d = seed(),
    p = d.profiles[0],
    date = dateAfter();
  assert.throws(
    () => validateBooking(p, d.services[1], date, "16:00", d.reservations),
    /ocupado/,
  );
  assert.throws(
    () => validateBooking(p, d.services[2], date, "16:00", d.reservations),
    /ocupado/,
  );
  assert.doesNotThrow(() =>
    validateBooking(
      p,
      d.services[1],
      date,
      "16:00",
      d.reservations,
      d.reservations[0].id,
    ),
  );
  assert.throws(
    () => validateBooking(p, d.services[0], "2000-01-01", "09:00", []),
    /fecha/,
  );
});
test("guest expiration, revocation and inactive host deny the DEMO scenario", () => {
  const d = seed(),
    p = d.profiles.find((p) => p.role === "GUEST");
  assert.equal(evaluateDemo(p, d).access, "authorized");
  d.invitations[0].status = "revoked";
  assert.equal(evaluateDemo(p, d).access, "denied");
  d.invitations[0].status = "active";
  d.invitations[0].valid_until = "2000-01-01";
  assert.equal(evaluateDemo(p, d).access, "denied");
  d.invitations[0].valid_until = new Date(Date.now() + 60000).toISOString();
  d.profiles[0].membership_status = "suspended";
  assert.equal(evaluateDemo(p, d).access, "denied");
});
test("staff and contractor only receive assigned zone and fail on missing/expired assignment", () => {
  const d = seed();
  for (const role of ["STAFF", "EXTERNAL"]) {
    const p = d.profiles.find((p) => p.role === role),
      w = d.work_assignments.find((w) => w.worker_id === p.id);
    const result = evaluateDemo(p, d);
    assert.equal(result.access, "authorized");
    assert.equal(result.destination, w.authorized_zone);
    assert.equal(result.robot_target, "robot1");
    w.valid_until = "2000-01-01";
    assert.equal(evaluateDemo(p, d).access, "denied");
  }
});
test("VIP handoff requires active identity; review or denial cannot target robot2", () => {
  const d = seed(),
    p = d.profiles[0];
  assert.equal(evaluateDemo(p, d).event_type, "vip_handoff");
  for (const outcome of ["review", "denied"]) {
    const r = evaluateDemo(p, d, outcome);
    assert.equal(r.robot_target, "robot1");
    assert.equal(r.destination, null);
  }
  p.membership_status = "inactive";
  assert.equal(evaluateDemo(p, d).access, "denied");
});
test("regular without today booking requires review", () => {
  const d = seed();
  assert.equal(evaluateDemo(d.profiles[1], d).access, "review");
});
test("access contracts fail closed on missing fields and mismatched simulation", () => {
  const decision = {
    visitor_id: "one",
    role: "VIP",
    access: "authorized",
    destination: "VIP_LOUNGE",
    robot_target: "robot2",
    event_type: "vip_handoff",
    simulation: true,
  };
  assert.equal(validateDecision(decision, true), decision);
  assert.throws(() => validateDecision(decision, false), /simulación/);
  assert.throws(
    () => validateDecision({ ...decision, destination: null }, true),
    /destino/,
  );
  assert.throws(
    () => validateDecision({ ...decision, role: "ADMIN" }, true),
    /incompleta/,
  );
  assert.throws(
    () => validateDecision({ ...decision, role: "REGULAR" }, true),
    /inconsistente/,
  );
  assert.throws(
    () => validateDecision({ ...decision, access: "denied" }, true),
    /inconsistente/,
  );
});
test("rendered database text is escaped", () => {
  assert.equal(
    escape('<img onerror="alert(1)">'),
    "&lt;img onerror=&quot;alert(1)&quot;&gt;",
  );
});
test("event timestamps use Colombian date rather than UTC day", () => {
  assert.equal(dateLabel("2026-10-24T02:00:00Z"), "23 de octubre");
  assert.equal(dateLabel("2026-10-24"), "24 de octubre");
});
