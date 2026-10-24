import { supabase, configurationError } from "./config.js";
import { readDemo, writeDemo, demoBook } from "./demo.js";
import { uid, today, isMember, canUseApp } from "./lib.js";
import { api } from "./api.js";
import {
  personColumns, profileFromRow, serviceFromRow, reservationFromRow,
  invitationFromRow, assignmentFromRow, eventFromRow, bookingToRow,
  roleToCategory, categoryToRole, destinations,
} from "./schema.js";

const appAccessMessage =
  "El acceso es solo para miembros y administradores. Si eres invitado, personal o proveedor, recepción te ayudará con tu ingreso al club.";

export const sessionState = { mode: "live", profile: null };
export async function restoreSession() {
  if (sessionStorage.getItem("nclub-demo-profile")) {
    const p = readDemo().profiles.find(
      (p) => p.id === sessionStorage.getItem("nclub-demo-profile"),
    );
    if (canUseApp(p)) {
      sessionState.mode = "demo";
      sessionState.profile = p;
      return p;
    }
    sessionStorage.removeItem("nclub-demo-profile");
  }
  if (!supabase) return null;
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();
  if (sessionError || !session?.user?.id) return null;

  // Auth verification and the RLS-protected profile lookup are independent;
  // overlap them so a reload pays for one network round trip instead of two.
  const [authResult, profileResult] = await Promise.allSettled([
    supabase.auth.getUser(),
    loadProfile(session.user.id),
  ]);
  const auth = authResult.status === "fulfilled" ? authResult.value : null;
  if (
    !auth ||
    auth.error ||
    auth.data.user?.id !== session.user.id
  ) {
    sessionState.profile = null;
    sessionState.mode = "live";
    await supabase.auth.signOut();
    return null;
  }
  if (profileResult.status === "rejected") throw profileResult.reason;
  return profileResult.value;
}
async function loadProfile(authId) {
  const { data, error } = await supabase
    .from("personas")
    .select(personColumns)
    .eq("auth_user_id", authId)
    .single();
  if (error || !canUseApp({ role: categoryToRole[data?.categoria] })) {
    sessionState.profile = null;
    sessionState.mode = "live";
    await supabase.auth.signOut();
    throw new Error(appAccessMessage);
  }
  const memberships = data.categoria === "ADMIN" ? [] : unwrap(
    await supabase.from("membresias").select("*").eq("persona_id", data.id),
  );
  sessionState.mode = "live";
  sessionState.profile = profileFromRow(data, memberships);
  return sessionState.profile;
}
export async function login(email, password) {
  if (!supabase) throw new Error(configurationError);
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });
  if (error) throw error;
  sessionStorage.removeItem("nclub-demo-profile");
  return loadProfile(data.user.id);
}
export function loginDemo(id) {
  const p = readDemo().profiles.find((p) => p.id === id);
  if (!p) throw new Error("Perfil DEMO inexistente.");
  if (!canUseApp(p)) throw new Error(appAccessMessage);
  sessionStorage.setItem("nclub-demo-profile", id);
  sessionState.mode = "demo";
  sessionState.profile = p;
  return p;
}
export async function logout() {
  sessionStorage.removeItem("nclub-demo-profile");
  if (supabase) await supabase.auth.signOut();
  sessionState.profile = null;
  sessionState.mode = "live";
}
function unwrap({ data, error }) {
  if (error) throw error;
  return data;
}
export async function loadData() {
  if (!canUseApp(sessionState.profile)) throw new Error(appAccessMessage);
  if (sessionState.mode === "demo") {
    const data = readDemo();
    const p = data.profiles.find((p) => p.id === sessionState.profile?.id);
    if (!canUseApp(p)) {
      sessionStorage.removeItem("nclub-demo-profile");
      sessionState.profile = null;
      throw new Error(appAccessMessage);
    }
    sessionState.profile = p;
    return data;
  }
  const p = sessionState.profile;
  if (!p) throw new Error("Inicia sesión para continuar.");
  const admin = p.role === "ADMIN";
  const tables = [
    "personas",
    "membresias",
    "servicios",
    "reservas",
    "eventos_acceso",
    "invitaciones",
    "permisos_laborales",
  ];
  const results = await Promise.all(
    tables.map((table) => {
      if (!admin && ["invitaciones", "permisos_laborales"].includes(table)) return [];
      let query = supabase.from(table).select(table === "personas" ? personColumns : "*");
      if (!admin && table === "personas") query = query.eq("id", p.id);
      if (!admin && ["membresias", "reservas", "eventos_acceso"].includes(table)) query = query.eq("persona_id", p.id);
      if (table === "eventos_acceso")
        query = query.order("created_at", { ascending: false }).limit(80);
      return query.then(unwrap);
    }),
  );
  const rows = Object.fromEntries(tables.map((t, i) => [t, results[i]]));
  const data = {
    profiles: rows.personas.map((p) => profileFromRow(p, rows.membresias)),
    services: rows.servicios.map(serviceFromRow),
    reservations: rows.reservas.map(reservationFromRow),
    access_events: rows.eventos_acceso.map(eventFromRow),
    invitations: rows.invitaciones.map(invitationFromRow),
    work_assignments: rows.permisos_laborales.map(assignmentFromRow),
  };
  for (const row of rows.reservas.filter((r) => !r.servicio_id))
    data.services.push({ id: `legacy-${row.id}`, name: row.actividad, category: "legacy", active: false });
  const current = data.profiles.find((x) => x.id === p.id);
  if (!canUseApp(current)) {
    await logout();
    throw new Error(appAccessMessage);
  }
  sessionState.profile = current;
  return data;
}
export async function book(serviceId, date, time, id) {
  if (sessionState.mode === "demo")
    return demoBook(sessionState.profile, serviceId, date, time, id);
  const payload = bookingToRow(sessionState.profile.id, serviceId, date, time);
  const { persona_id, ...changes } = payload;
  return unwrap(
    await (
      id
        ? supabase.from("reservas").update(changes).eq("id", id)
        : supabase.from("reservas").insert(payload)
    )
      .select()
      .single(),
  );
}
export async function cancel(id) {
  if (sessionState.mode === "demo") {
    const data = readDemo();
    const r = data.reservations.find(
      (r) =>
        r.id === id &&
        (r.user_id === sessionState.profile.id ||
          sessionState.profile.role === "ADMIN"),
    );
    if (!r) throw new Error("Reserva no encontrada.");
    r.status = "cancelled";
    writeDemo(data);
    return;
  }
  unwrap(
    await supabase
      .from("reservas")
      .update({ estado: "CANCELADA" })
      .eq("id", id)
      .select()
      .single(),
  );
}
export async function availability(serviceId, date) {
  if (sessionState.mode === "demo")
    return readDemo()
      .reservations.filter(
        (r) =>
          r.service_id === serviceId &&
          r.reservation_date === date &&
          r.status === "confirmed",
      )
      .map((r) => ({ start_time: r.start_time, end_time: r.end_time }));
  return unwrap(
    await supabase.rpc("consultar_disponibilidad", {
      p_servicio: serviceId,
      p_fecha: date,
    }),
  );
}
export async function issueCredential(userId = sessionState.profile.id) {
  if (sessionState.mode === "demo") {
    const data = readDemo();
    const profile = data.profiles.find((p) => p.id === userId);
    if (!profile || profile.membership_status !== "active")
      throw new Error("La identidad no está activa.");
    if (
      sessionState.profile.id !== userId &&
      sessionState.profile.role !== "ADMIN"
    )
      throw new Error("No autorizado.");
    const token = `demo_${uid()}${uid()}`;
    data.credentials
      .filter((c) => c.user_id === userId)
      .forEach((c) => (c.revoked_at = new Date().toISOString()));
    data.credentials.push({
      id: uid(),
      user_id: userId,
      token,
      expires_at: new Date(Date.now() + 3600000).toISOString(),
      revoked_at: null,
    });
    writeDemo(data);
    return { token, expires_at: new Date(Date.now() + 3600000).toISOString() };
  }
  return unwrap(await supabase.rpc("emitir_credencial", { p_persona_id: userId }));
}
export async function updateProfile(id, values) {
  if (sessionState.profile.role !== "ADMIN")
    throw new Error("Solo administradores.");
  const allowed = {
    full_name: values.full_name,
    membership_status: values.membership_status,
    email: values.email?.trim().toLowerCase() || null,
    phone: values.telefono?.trim() || null,
    document_type: values.tipo_documento || null,
    document_number: values.numero_documento?.replace(/[^a-z0-9]/gi, "").toUpperCase() || null,
    position: values.cargo?.trim() || null,
    membership_expires_at: values.vigencia_hasta
      ? `${values.vigencia_hasta}T23:59:59-05:00`
      : null,
  };
  if (sessionState.mode === "demo") {
    const d = readDemo();
    Object.assign(
      d.profiles.find((p) => p.id === id),
      allowed,
    );
    writeDemo(d);
    return;
  }
  return unwrap(
    await supabase.rpc("actualizar_persona", {
      p_id: id,
      p_nombre: allowed.full_name,
      p_estado: allowed.membership_status,
      p_email: allowed.email,
      p_telefono: allowed.phone,
      p_tipo_documento: allowed.document_type,
      p_numero_documento: allowed.document_number,
      p_cargo: allowed.position,
      p_vigencia_hasta: allowed.membership_expires_at,
    }),
  );
}
function colombiaTimestamp(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))
    throw new Error("Completa las fechas y horas de inicio y final.");
  return `${value}:00-05:00`;
}
export async function updateAuthorizationDates(table, id, values) {
  if (sessionState.profile?.role !== "ADMIN") throw new Error("Solo administradores.");
  if (!["invitations", "work_assignments"].includes(table)) throw new Error("Tipo de autorización no válido.");
  const valid_from = colombiaTimestamp(values.valid_from);
  const valid_until = colombiaTimestamp(values.valid_until);
  const start = Date.parse(valid_from);
  const end = Date.parse(valid_until);
  if (end <= start) throw new Error("La fecha final debe ser posterior a la inicial.");
  if (end - start > 7 * 24 * 60 * 60 * 1000) throw new Error("La vigencia no puede superar 7 días.");
  if (sessionState.mode === "demo") {
    const demo = readDemo();
    const row = demo[table].find((item) => item.id === id);
    if (!row || row.status !== "active") throw new Error("La autorización ya no está activa.");
    row.valid_from = valid_from;
    row.valid_until = valid_until;
    if (table === "invitations") row.visit_date = valid_from.slice(0, 10);
    writeDemo(demo);
    return;
  }
  const body = { valid_from, valid_until };
  if (table === "invitations") return api.updateInvitationDates(id, body);
  return api.updateExternalAssignmentDates(id, body);
}
export async function createVisitor(values) {
  if (sessionState.profile.role !== "ADMIN")
    throw new Error("Solo administradores.");
  if (new Date(values.valid_until) <= new Date(values.valid_from))
    throw new Error("La hora final debe ser posterior a la inicial.");
  if (sessionState.mode !== "demo")
    return unwrap(
      await supabase.rpc("crear_visitante", {
        p_nombre: values.name,
        p_categoria: roleToCategory[values.role],
        p_anfitrion: values.host_id || null,
        p_empresa: values.company || null,
        p_desde: values.valid_from,
        p_hasta: values.valid_until,
        p_destino: destinations[values.destination] || values.destination,
        p_email: values.email?.trim().toLowerCase() || null,
        p_telefono: values.telefono?.trim() || null,
        p_tipo_documento: values.tipo_documento,
        p_numero_documento: values.numero_documento?.replace(/[^a-z0-9]/gi, "").toUpperCase(),
      }),
    );
  const d = readDemo();
  const documentNumber = values.numero_documento?.replace(/[^a-z0-9]/gi, "").toUpperCase();
  const existing = d.profiles.find((p) => p.document_type === values.tipo_documento && p.document_number === documentNumber);
  if (existing && existing.role !== values.role)
    throw new Error("Ese documento ya está registrado con otra categoría de persona.");
  if (existing && values.role === "GUEST" && d.invitations.some((invitation) => invitation.guest_id === existing.id && invitation.status === "active" && new Date(invitation.valid_until) > new Date()))
    throw new Error("Esta persona ya tiene una invitación vigente.");
  const id = existing?.id || uid();
  const person = {
    id,
    full_name: values.name,
    role: values.role,
    membership_status: "active",
    public_id: existing?.public_id || `NC-${id.slice(0, 6).toUpperCase()}`,
    created_at: existing?.created_at || new Date().toISOString(),
    email: values.email?.trim().toLowerCase() || null,
    phone: values.telefono?.trim() || null,
    document_type: values.tipo_documento,
    document_number: documentNumber,
    position: values.company?.trim() || null,
  };
  if (existing) Object.assign(existing, person);
  else d.profiles.push(person);
  if (values.role === "GUEST") {
    if (
      !d.profiles.some(
        (p) =>
          p.id === values.host_id &&
          isMember(p) &&
          p.membership_status === "active",
      )
    )
      throw new Error("Anfitrión no válido.");
    d.invitations.push({
      id: uid(),
      guest_id: id,
      host_id: values.host_id,
      visit_date: values.valid_from.slice(0, 10),
      valid_from: values.valid_from,
      valid_until: values.valid_until,
      destination: values.destination,
      status: "active",
    });
  } else
    d.work_assignments.push({
      id: uid(),
      worker_id: id,
      company: values.company,
      assignment_type: values.role === "STAFF" ? "SHIFT" : "EXTERNAL_ORDER",
      valid_from: values.valid_from,
      valid_until: values.valid_until,
      authorized_zone: values.destination,
      status: "active",
    });
  writeDemo(d);
  const credential = await issueCredential(id);
  return { ...credential, user_id: id };
}
export async function revoke(table, id) {
  if (
    sessionState.profile.role !== "ADMIN" ||
    !["invitations", "work_assignments"].includes(table)
  )
    throw new Error("No autorizado.");
  if (sessionState.mode === "demo") {
    const d = readDemo();
    d[table].find((r) => r.id === id).status = "revoked";
    writeDemo(d);
    return;
  }
  unwrap(
    await supabase
      .from(table === "invitations" ? "invitaciones" : "permisos_laborales")
      .update({ estado: table === "invitations" ? "CANCELADA" : "CANCELADO" })
      .eq(table === "invitations" ? "codigo_qr" : "codigo_autorizacion", id)
      .select()
      .single(),
  );
}
export function appendDemoEvent(decision) {
  if (sessionState.mode !== "demo" || sessionState.profile.role !== "ADMIN")
    throw new Error("Disponible solo en administración DEMO.");
  const d = readDemo();
  d.access_events.unshift({
    id: uid(),
    visitor_id: decision.visitor_id,
    role: decision.role,
    event_type: decision.event_type,
    access_status: decision.access,
    destination: decision.destination,
    robot_target: decision.robot_target,
    simulation: true,
    created_at: new Date().toISOString(),
  });
  writeDemo(d);
}
