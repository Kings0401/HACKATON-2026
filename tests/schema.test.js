import test from "node:test";
import assert from "node:assert/strict";
import {
  categoryToRole, roleToCategory, profileFromRow, serviceFromRow,
  reservationFromRow, invitationFromRow, assignmentFromRow, eventFromRow,
  bookingToRow,
} from "../src/schema.js";

test("native categories map to app roles without giving visitors app access", () => {
  assert.deepEqual(categoryToRole, {
    VIP: "VIP", REGULAR: "REGULAR", INVITADO: "GUEST",
    PERSONAL_INTERNO: "STAFF", TRABAJADOR_EXTERNO: "EXTERNAL", ADMIN: "ADMIN",
  });
  assert.equal(roleToCategory.EXTERNAL, "TRABAJADOR_EXTERNO");
  assert.equal(roleToCategory.GUEST, "INVITADO");
});
test("membership presentation follows category, suspension, activity and expiry", () => {
  const person = { id: "VIP001", nombre: "Valeria Torres", categoria: "VIP", activo: true };
  const valid = { persona_id: "VIP001", nivel: "VIP", estado: "ACTIVA", vigencia_hasta: new Date(Date.now() + 86400000).toISOString() };
  assert.equal(profileFromRow(person, [valid]).membership_status, "active");
  assert.equal(profileFromRow(person, [{ ...valid, estado: "SUSPENDIDA" }]).membership_status, "suspended");
  assert.equal(profileFromRow(person, [{ ...valid, vigencia_hasta: "2000-01-01" }]).membership_status, "inactive");
  assert.equal(profileFromRow(person, [{ ...valid, nivel: "REGULAR" }]).membership_status, "inactive");
  assert.equal(profileFromRow({ ...person, activo: false }, [valid]).membership_status, "inactive");
  assert.equal(profileFromRow(person, []).membership_status, "inactive");
  assert.equal(profileFromRow({ ...person, categoria: "ADMIN" }, []).role, "ADMIN");
});
test("reservation mapping keeps text IDs and uses Colombian dates across UTC midnight", () => {
  const mapped = reservationFromRow({ id: "RES001", persona_id: "VIP001", servicio_id: "lounge", fecha_inicio: "2026-10-24T02:00:00Z", fecha_fin: "2026-10-24T03:00:00Z", estado: "CONFIRMADA" });
  assert.equal(mapped.reservation_date, "2026-10-23");
  assert.equal(mapped.start_time, "21:00");
  assert.equal(mapped.end_time, "22:00");
  assert.equal(mapped.user_id, "VIP001");
  assert.equal(mapped.legacy, false);
  assert.equal(reservationFromRow({ id: "OLD", persona_id: "REG001", fecha_inicio: "2026-10-24T02:00:00Z", fecha_fin: "2026-10-24T11:00:00Z", estado: "CONFIRMADA" }).legacy, true);
  assert.deepEqual(bookingToRow("REG001", "golf-1", "2026-10-25", "17:00"), {
    persona_id: "REG001", servicio_id: "golf-1", fecha_inicio: "2026-10-25T17:00:00-05:00", fecha_fin: "2026-10-25T18:00:00-05:00", estado: "CONFIRMADA",
  });
});
test("invitation/work authorization mapping preserves revocation and escort requirements", () => {
  assert.equal(invitationFromRow({ codigo_qr: "QR-INV-001", persona_id: "INV001", anfitrion_id: "VIP001", valido_desde: "2026-10-24T02:00:00Z", estado: "UTILIZADA" }).status, "revoked");
  const work = assignmentFromRow({ codigo_autorizacion: "QR-EXT-001", persona_id: "EXT001", tipo: "TRABAJADOR_EXTERNO", requiere_acompanamiento: true, estado: "CANCELADO" });
  assert.equal(work.status, "revoked");
  assert.equal(work.requires_escort, true);
  assert.equal(work.assignment_type, "EXTERNAL_ORDER");
});
test("native catalog and access decisions map to the existing presentation contract", () => {
  assert.equal(serviceFromRow({ id: "restaurant", categoria: "RESTAURANTE" }).category, "restaurant");
  const event = eventFromRow({ id: "event", persona_id: "EXT001", categoria: "TRABAJADOR_EXTERNO", tipo_evento: "arrival", estado_acceso: "REVISION", destino: "Zona técnica", robot: "robot1", simulacion: false });
  assert.equal(event.visitor_id, "EXT001");
  assert.equal(event.access_status, "review");
  assert.equal(event.simulation, false);
  assert.equal(event.role, "EXTERNAL");
});
