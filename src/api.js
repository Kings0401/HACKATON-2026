import { backendUrl, supabase } from "./config.js";

// Token ADMIN del backend en modo memoria (lo imprime uvicorn). Solo para
// pruebas con datos ficticios desde una sesión DEMO; nunca un secreto real.
const MEMORY_TOKEN = "nclub-backend-memory-token";
export const memoryToken = {
  get: () => {
    try {
      return sessionStorage.getItem(MEMORY_TOKEN) || "";
    } catch {
      return "";
    }
  },
  set: (value) => {
    try {
      if (value) sessionStorage.setItem(MEMORY_TOKEN, value.trim());
      else sessionStorage.removeItem(MEMORY_TOKEN);
    } catch {
      /* Sin almacenamiento, el token debe volver a escribirse. */
    }
  },
};

export async function request(
  path,
  { method = "GET", body, binary, contentType, anonymous = false, timeout = 10000 } = {},
) {
  if (!backendUrl) throw new Error("FastAPI no está configurado.");
  const session = anonymous
    ? null
    : (await supabase?.auth.getSession())?.data?.session;
  const token = session?.access_token || (anonymous ? "" : memoryToken.get());
  const response = await fetch(`${backendUrl}${path}`, {
    method,
    headers: {
      "Content-Type": binary ? contentType || "application/octet-stream" : "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(binary ? { body: binary } : body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(timeout),
    cache: "no-store",
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof json.detail === "string"
        ? json.detail
        : `Backend: error ${response.status}`,
    );
  return json;
}
export const api = {
  health: () => request("/health", { anonymous: true }),
  robotMonitor: () => request("/robot/monitor"),
  robotStatus: () => request("/robot/status", { anonymous: true, timeout: 5000 }),
  recognition: (body) => request("/recognition", { method: "POST", body }),
  validate: (body) => request("/validate", { method: "POST", body }),
  check: (body) => request("/access/check", { method: "POST", body }),
  event: (body) => request("/events", { method: "POST", body }),
  vipContext: (id) => request(`/vip/context/${encodeURIComponent(id)}`),
  labStatus: () => request("/admin/lab/status"),
  labFrame: (jpeg) =>
    request("/admin/lab/frame", { method: "POST", binary: jpeg, contentType: "image/jpeg", timeout: 15000 }),
  labText: (text) => request("/admin/lab/text", { method: "POST", body: { text } }),
  labReset: () => request("/admin/lab/reset", { method: "POST" }),
  createMember: (body) => request("/admin/members", { method: "POST", body }),
  memberCredential: (id) =>
    request(`/admin/personas/${encodeURIComponent(id)}/credential`, { method: "POST" }),
  uploadPhoto: (id, jpeg) =>
    request(`/admin/personas/${encodeURIComponent(id)}/photos?consent=true`, {
      method: "POST",
      binary: jpeg,
      contentType: "image/jpeg",
      timeout: 30000,
    }),
  assistance: async () => {
    const result = await request("/events", {
      method: "POST",
      body: { event_type: "assistance_requested" },
    });
    if (result.accepted !== true)
      throw new Error("El backend no confirmó la solicitud de atención.");
    return result;
  },
};
export function validateDecision(value, simulation) {
  if (
    !value ||
    !["authorized", "review", "denied", "pending"].includes(value.access) ||
    !["VIP", "REGULAR", "GUEST", "STAFF", "EXTERNAL"].includes(value.role) ||
    typeof value.visitor_id !== "string" ||
    !value.visitor_id ||
    typeof value.event_type !== "string" ||
    !value.event_type ||
    typeof value.simulation !== "boolean" ||
    value.simulation !== simulation
  )
    throw new Error(
      "Respuesta de acceso incompleta o modo de simulación incorrecto. No se ha autorizado el ingreso.",
    );
  if (
    value.access === "authorized" &&
    (!value.destination || !["robot1", "robot2"].includes(value.robot_target))
  )
    throw new Error("Falta destino o robot en la autorización.");
  if (
    (value.event_type === "vip_handoff" || value.robot_target === "robot2") &&
    (value.role !== "VIP" ||
      value.access !== "authorized" ||
      value.robot_target !== "robot2" ||
      value.event_type !== "vip_handoff")
  )
    throw new Error(
      "Transferencia VIP inconsistente. Se requiere revisión del backend.",
    );
  return value;
}
