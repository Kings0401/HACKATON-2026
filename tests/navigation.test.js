import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { computeRoute, mapSvg, routeCard } from "../src/navigation.js";

const expected = JSON.parse(
  await readFile(new URL("./fixtures/routes-python.json", import.meta.url), "utf8"),
);

test("JS routes match the FastAPI (Python) routes for every category and destination", () => {
  for (const c of expected) {
    if (c.error) {
      assert.throws(() => computeRoute(c.category, c.destination, { escort: c.escort }), undefined, JSON.stringify(c));
      continue;
    }
    const r = computeRoute(c.category, c.destination, { escort: c.escort });
    assert.deepEqual(
      { path: r.path, steps: r.steps.map((s) => s.action), distance_m: r.distance_m, minutes: r.minutes },
      { path: c.path, steps: c.steps, distance_m: c.distance_m, minutes: c.minutes },
      `${c.category} → ${c.destination}`,
    );
  }
});

test("restricted zones are never crossed and are drawn as locked", () => {
  const r = computeRoute("TRABAJADOR_EXTERNO", "Zona técnica", { escort: true });
  assert.ok(!r.path.some((n) => ["lobby", "galeria", "restaurante"].includes(n)));
  assert.equal(r.steps.find((s) => s.action === "wait_escort").node, "recepcion_proveedores");
  const svg = mapSvg(r);
  assert.match(svg, /CASA CLUB · RESTRINGIDO/);
  assert.match(svg, /SIMULADO/);
  assert.throws(() => computeRoute("REGULAR", "VIP Lounge"));
});

test("route card escapes text and offers the phone QR only when requested", () => {
  const r = computeRoute("INVITADO", "Restaurante principal");
  assert.match(routeCard(r, { qrId: "q1" }), /id="q1"/);
  assert.doesNotMatch(routeCard(r), /<canvas/);
  assert.match(routeCard({ error: "x", destination: "<b>" }), /&lt;b&gt;/);
});
