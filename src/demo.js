import { uid, dateAfter, today, validateBooking, canBook } from "./lib.js";

const KEY = "nclub-demo-v1";
export const demoPeople = [
  ["VIP", "Gabriela", "Montenegro", "gabriela@nclub.demo"],
  ["REGULAR", "Alejandro", "Ríos", "alejandro@nclub.demo"],
  ["GUEST", "Isabella", "Vargas", "isabella@nclub.demo"],
  ["STAFF", "Camila", "Torres", "camila@nclub.demo"],
  ["EXTERNAL", "Daniel", "Medina", "daniel@nclub.demo"],
  ["ADMIN", "Sofía", "Restrepo", "sofia@nclub.demo"],
];
export function seed() {
  const profiles = demoPeople.map(([role, first, last, email], i) => ({
    id: `demo-${role.toLowerCase()}`,
    full_name: `${first} ${last}`,
    email,
    role,
    membership_status: "active",
    created_at: new Date().toISOString(),
    public_id: `NC-${String(1001 + i)}`,
    position:
      role === "STAFF"
        ? "Hospitalidad y gastronomía"
        : role === "EXTERNAL"
          ? "Técnico de mantenimiento"
          : "",
    facial_consent: false,
  }));
  const services = [1, 2, 3, 4, 5].map((i) => ({
    id: `golf-${i}`,
    name: `Campo de golf · Cancha ${i}`,
    description: [
      "Un recorrido entre naturaleza y precisión.",
      "Nuestro recorrido insignia. Cada hoyo, una nueva perspectiva.",
      "Un desafío excepcional junto al lago.",
      "La tranquilidad de jugar a tu ritmo.",
      "El escenario perfecto para mejorar tu juego.",
    ][i - 1],
    category: "golf",
    vip_only: false,
    active: true,
    image: "/images/course.jpg",
  }));
  services.push(
    {
      id: "restaurant",
      name: "Restaurante N Club",
      description: "Sabores de temporada, momentos que permanecen.",
      category: "restaurant",
      vip_only: false,
      active: true,
      image: "/images/restaurant.jpg",
    },
    {
      id: "lounge",
      name: "Lounge VIP",
      description: "Un espacio reservado para lo extraordinario.",
      category: "lounge",
      vip_only: true,
      active: true,
      image: "/images/lounge.jpg",
    },
  );
  return {
    profiles,
    services,
    reservations: [
      {
        id: uid(),
        user_id: profiles[0].id,
        service_id: "golf-2",
        reservation_date: dateAfter(),
        start_time: "16:00",
        end_time: "17:00",
        status: "confirmed",
        created_at: new Date().toISOString(),
      },
      {
        id: uid(),
        user_id: profiles[1].id,
        service_id: "golf-1",
        reservation_date: dateAfter(),
        start_time: "10:00",
        end_time: "11:00",
        status: "confirmed",
        created_at: new Date().toISOString(),
      },
    ],
    invitations: [
      {
        id: uid(),
        guest_id: profiles[2].id,
        host_id: profiles[0].id,
        visit_date: today(),
        valid_from: `${today()}T00:00:00-05:00`,
        valid_until: `${today()}T23:59:59-05:00`,
        destination: "RESTAURANT",
        status: "active",
      },
    ],
    work_assignments: [
      {
        id: uid(),
        worker_id: profiles[3].id,
        company: "N Club World",
        assignment_type: "SHIFT",
        valid_from: `${today()}T00:00:00-05:00`,
        valid_until: `${today()}T23:59:59-05:00`,
        authorized_zone: "KITCHEN",
        status: "active",
      },
      {
        id: uid(),
        worker_id: profiles[4].id,
        company: "Green Systems",
        assignment_type: "EXTERNAL_ORDER",
        valid_from: `${today()}T00:00:00-05:00`,
        valid_until: `${today()}T23:59:59-05:00`,
        authorized_zone: "MAINTENANCE",
        status: "active",
      },
    ],
    access_events: [],
    credentials: [],
  };
}
export function readDemo() {
  try {
    const data = JSON.parse(localStorage.getItem(KEY));
    if (data?.profiles && data?.services) return data;
  } catch {
    /* Restore only the isolated demo store. */
  }
  const data = seed();
  writeDemo(data);
  return data;
}
export function writeDemo(data) {
  localStorage.setItem(KEY, JSON.stringify(data));
  window.dispatchEvent(new Event("nclub-demo-change"));
}
export function resetDemo() {
  const data = seed();
  writeDemo(data);
  return data;
}
export function demoBook(profile, serviceId, date, time, id) {
  const data = readDemo();
  const current = data.profiles.find((p) => p.id === profile.id);
  const service = data.services.find((s) => s.id === serviceId);
  validateBooking(current, service, date, time, data.reservations, id);
  const row = {
    id: id || uid(),
    user_id: profile.id,
    service_id: serviceId,
    reservation_date: date,
    start_time: time,
    end_time: `${String(Number(time.slice(0, 2)) + 1).padStart(2, "0")}:00`,
    status: "confirmed",
    created_at: new Date().toISOString(),
  };
  if (id) {
    const old = data.reservations.find(
      (r) => r.id === id && r.user_id === profile.id,
    );
    if (!old || old.status !== "confirmed")
      throw new Error("Reserva no disponible.");
    Object.assign(old, row);
  } else data.reservations.push(row);
  writeDemo(data);
  return row;
}
// Only fictitious results. This function must never be used for physical access.
export function evaluateDemo(profile, data, outcome = "authorized") {
  let access = outcome,
    destination = null,
    reason = "Validación DEMO completada.";
  const now = new Date();
  if (profile.membership_status !== "active") {
    access = "denied";
    reason = "Identidad o membresía inactiva.";
  } else if (["VIP", "REGULAR"].includes(profile.role)) {
    const reservation = data.reservations.find(
      (r) =>
        r.user_id === profile.id &&
        r.status === "confirmed" &&
        r.reservation_date === today() &&
        new Date(`${r.reservation_date}T${r.end_time}-05:00`) > now,
    );
    if (profile.role === "VIP") destination = "VIP_LOUNGE";
    else if (reservation)
      destination = data.services.find(
        (s) => s.id === reservation.service_id,
      )?.name;
    else {
      access = outcome === "authorized" ? "review" : outcome;
      reason = "Sin reserva vigente para hoy. Revisión en recepción.";
    }
  } else if (profile.role === "GUEST") {
    const invite = data.invitations.find(
      (i) =>
        i.guest_id === profile.id &&
        i.status === "active" &&
        new Date(i.valid_from) <= now &&
        new Date(i.valid_until) > now &&
        data.profiles.some(
          (p) =>
            p.id === i.host_id &&
            p.membership_status === "active" &&
            ["VIP", "REGULAR"].includes(p.role),
        ),
    );
    if (!invite) {
      access = "denied";
      reason = "Invitación vencida, revocada o anfitrión no autorizado.";
    } else destination = invite.destination;
  } else {
    const assignment = data.work_assignments.find(
      (w) =>
        w.worker_id === profile.id &&
        w.assignment_type ===
          (profile.role === "STAFF" ? "SHIFT" : "EXTERNAL_ORDER") &&
        w.status === "active" &&
        new Date(w.valid_from) <= now &&
        new Date(w.valid_until) > now,
    );
    if (!assignment) {
      access = "denied";
      reason = "No hay turno u orden vigente.";
    } else destination = assignment.authorized_zone;
  }
  return {
    visitor_id: profile.id,
    role: profile.role,
    access,
    destination: access === "authorized" ? destination : null,
    robot_target:
      access === "authorized" && profile.role === "VIP" ? "robot2" : "robot1",
    event_type:
      access === "authorized" && profile.role === "VIP"
        ? "vip_handoff"
        : `access_${access}`,
    simulation: true,
    reason,
  };
}
