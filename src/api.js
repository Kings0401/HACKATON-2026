import { backendUrl, supabase } from "./config.js";

export async function request(
  path,
  { method = "GET", body, anonymous = false } = {},
) {
  if (!backendUrl) throw new Error("FastAPI no está configurado.");
  const session = anonymous
    ? null
    : (await supabase?.auth.getSession())?.data?.session;
  const response = await fetch(`${backendUrl}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(10000),
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
  recognition: (body) => request("/recognition", { method: "POST", body }),
  validate: (body) => request("/validate", { method: "POST", body }),
  check: (body) => request("/access/check", { method: "POST", body }),
  event: (body) => request("/events", { method: "POST", body }),
  vipContext: (id) => request(`/vip/context/${encodeURIComponent(id)}`),
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
