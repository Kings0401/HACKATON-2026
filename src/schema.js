// Adaptación de las tablas reales en español a los modelos de presentación.
export const personColumns =
  "id,nombre,categoria,activo,created_at,auth_user_id,email,telefono,tipo_documento,numero_documento,cargo";
export const categoryToRole = {
  VIP: "VIP",
  REGULAR: "REGULAR",
  INVITADO: "GUEST",
  PERSONAL_INTERNO: "STAFF",
  TRABAJADOR_EXTERNO: "EXTERNAL",
  ADMIN: "ADMIN",
};
export const roleToCategory = Object.fromEntries(
  Object.entries(categoryToRole).map(([category, role]) => [role, category]),
);
export const destinations = {
  RESTAURANT: "Restaurante principal",
  GOLF_RECEPTION: "Recepción de golf",
  KITCHEN: "Cocina",
  RECEPTION: "Recepción",
  GOLF_OPERATIONS: "Operación de golf",
  MAINTENANCE: "Mantenimiento",
  SERVICE_ENTRANCE: "Entrada de servicio",
};
export function profileFromRow(p, memberships = []) {
  const membership = memberships.find((m) => m.persona_id === p.id);
  const member = ["VIP", "REGULAR"].includes(p.categoria);
  const membership_status = !p.activo
    ? "inactive"
    : member && membership?.estado === "SUSPENDIDA"
      ? "suspended"
      : member &&
          (!membership ||
            membership.nivel !== p.categoria ||
            !(new Date(membership.vigencia_hasta).getTime() > Date.now()))
        ? "inactive"
        : "active";
  return {
    id: p.id,
    public_id: p.id,
    auth_user_id: p.auth_user_id,
    full_name: p.nombre,
    email: p.email,
    phone: p.telefono,
    document_type: p.tipo_documento,
    document_number: p.numero_documento,
    role: categoryToRole[p.categoria],
    membership_status,
    membership_expires_at: membership?.vigencia_hasta,
    position: p.cargo,
    created_at: p.created_at,
  };
}
export const serviceFromRow = (s) => ({
  id: s.id,
  name: s.nombre,
  description: s.descripcion,
  category: { GOLF: "golf", RESTAURANTE: "restaurant", LOUNGE: "lounge" }[
    s.categoria
  ],
  vip_only: s.exclusivo_vip,
  active: s.activo,
  image: s.imagen,
});
const dateTime = (value) => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Bogota",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(value)).map(({ type, value }) => [type, value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
};
export const reservationFromRow = (r) => ({
  id: r.id,
  user_id: r.persona_id,
  service_id: r.servicio_id || `legacy-${r.id}`,
  reservation_date: dateTime(r.fecha_inicio).date,
  start_time: dateTime(r.fecha_inicio).time,
  end_time: dateTime(r.fecha_fin).time,
  status: r.estado === "CONFIRMADA" ? "confirmed" : "cancelled",
  legacy: !r.servicio_id || new Date(r.fecha_fin) - new Date(r.fecha_inicio) !== 3600000,
  created_at: r.created_at,
});
export const invitationFromRow = (r) => ({
  id: r.codigo_qr,
  guest_id: r.persona_id,
  host_id: r.anfitrion_id,
  visit_date: dateTime(r.valido_desde).date,
  valid_from: r.valido_desde,
  valid_until: r.valido_hasta,
  destination: r.destino,
  status: r.estado === "ACTIVA" ? "active" : "revoked",
  created_at: r.created_at,
});
export const assignmentFromRow = (r) => ({
  id: r.codigo_autorizacion,
  worker_id: r.persona_id,
  company: r.empresa,
  assignment_type: r.tipo === "PERSONAL_INTERNO" ? "SHIFT" : "EXTERNAL_ORDER",
  valid_from: r.valido_desde,
  valid_until: r.valido_hasta,
  authorized_zone: r.destino,
  requires_escort: r.requiere_acompanamiento,
  status: r.estado === "ACTIVO" ? "active" : "revoked",
});
export const eventFromRow = (r) => ({
  id: r.id,
  visitor_id: r.persona_id,
  role: categoryToRole[r.categoria],
  event_type: r.tipo_evento,
  access_status: {
    PENDIENTE: "pending",
    AUTORIZADO: "authorized",
    DENEGADO: "denied",
    REVISION: "review",
  }[r.estado_acceso],
  destination: r.destino,
  robot_target: r.robot,
  simulation: r.simulacion,
  created_at: r.created_at,
});
export function bookingToRow(userId, serviceId, date, time) {
  const hour = Number(time.slice(0, 2));
  return {
    persona_id: userId,
    servicio_id: serviceId,
    fecha_inicio: `${date}T${time}:00-05:00`,
    fecha_fin: `${date}T${String(hour + 1).padStart(2, "0")}:00:00-05:00`,
    estado: "CONFIRMADA",
  };
}
