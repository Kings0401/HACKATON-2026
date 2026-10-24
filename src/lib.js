export const roles = {
  VIP: "Miembro VIP",
  REGULAR: "Miembro",
  GUEST: "Invitado",
  STAFF: "Personal del club",
  EXTERNAL: "Trabajador externo",
  ADMIN: "Administrador",
};
export const escape = (value = "") =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const today = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export function dateAfter(days = 1) {
  const d = new Date(`${today()}T12:00:00-05:00`);
  d.setDate(d.getDate() + days);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}
export const dateLabel = (value) =>
  new Intl.DateTimeFormat("es-CO", {
    day: "numeric",
    month: "long",
    timeZone: "America/Bogota",
  }).format(
    new Date(
      String(value).includes("T")
        ? value
        : `${String(value).slice(0, 10)}T12:00:00-05:00`,
    ),
  );
export const timeLabel = (value) => `${String(value).slice(0, 5)}`;
export const clockLabel = (value) =>
  new Intl.DateTimeFormat("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "America/Bogota",
  }).format(new Date(value));
export const uid = () => crypto.randomUUID();
export const isMember = (p) => ["VIP", "REGULAR"].includes(p?.role);
export const canUseApp = (p) => isMember(p) || p?.role === "ADMIN";
export function canBook(profile, service) {
  return (
    isMember(profile) &&
    profile.membership_status === "active" &&
    service.active &&
    (!service.vip_only || profile.role === "VIP")
  );
}
export const slots = Array.from(
  { length: 10 },
  (_, i) => `${String(i + 8).padStart(2, "0")}:00`,
);
export function validateBooking(
  profile,
  service,
  date,
  time,
  reservations,
  exceptId,
) {
  if (!canBook(profile, service))
    throw new Error("Tu membresía no permite reservar este servicio.");
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    date < today() ||
    !slots.includes(time)
  )
    throw new Error("Selecciona una fecha futura y un horario válido.");
  if (new Date(`${date}T${time}:00-05:00`) <= new Date())
    throw new Error("Este horario ya ha pasado.");
  const busy = reservations.some(
    (r) =>
      r.id !== exceptId &&
      r.status === "confirmed" &&
      r.reservation_date === date &&
      r.start_time.slice(0, 5) === time &&
      (r.service_id === service.id || r.user_id === profile.id),
  );
  if (busy)
    throw new Error(
      "El horario ya está ocupado o coincide con otra de tus reservas.",
    );
}
export function readableError(error) {
  if (error?.code === "23P01" || error?.code === "23505")
    return "Ese horario acaba de ocuparse. Elige otro.";
  if (error?.message?.includes("Invalid login"))
    return "Correo o contraseña incorrectos.";
  if (error?.message?.includes("Failed to fetch"))
    return "No se pudo conectar. Revisa tu conexión e inténtalo otra vez.";
  return error?.message || "No fue posible completar la operación.";
}
export const images = {
  golf: "/images/golf.jpg",
  course: "/images/course.jpg",
  restaurant: "/images/restaurant.jpg",
  lounge: "/images/lounge.jpg",
};
