// Navegación interior: dibuja la ruta autorizada sobre el mapa esquemático.
// El cálculo oficial lo hace FastAPI (backend/app/services/navigation.py);
// esta copia del algoritmo solo se usa en DEMO, sin backend.
import clubMap from "../shared/club-map.json" with { type: "json" };
import { escape as e } from "./lib.js";
import { icon } from "./ui.js";

export const roleToCategory = {
  VIP: "VIP",
  REGULAR: "REGULAR",
  GUEST: "INVITADO",
  STAFF: "PERSONAL_INTERNO",
  EXTERNAL: "TRABAJADOR_EXTERNO",
};
const categoryLabel = {
  VIP: "VIP",
  REGULAR: "Miembro",
  INVITADO: "Invitado",
  PERSONAL_INTERNO: "Personal",
  TRABAJADOR_EXTERNO: "Proveedor",
};
const notes = {
  VIP: "Ruta preferente por el ala VIP. AGIBOT 02 le atenderá personalmente.",
  REGULAR: "Ruta por las áreas de socios hacia su actividad.",
  INVITADO:
    "Ruta limitada a las áreas de su invitación. Su anfitrión ha sido notificado.",
  PERSONAL_INTERNO: "Ruta por corredores de personal hacia su zona autorizada.",
  TRABAJADOR_EXTERNO:
    "Ruta exclusiva de servicio. No ingrese a áreas sociales.",
};
const turnText = {
  straight: "Continúe recto",
  left: "Gire a la izquierda",
  right: "Gire a la derecha",
  u_turn: "Dé la vuelta",
};
const stepIcon = {
  start: "map-pin",
  straight: "move-up",
  left: "corner-up-left",
  right: "corner-up-right",
  u_turn: "undo-2",
  arrive: "flag",
  wait_escort: "hourglass",
};

const nodes = clubMap.nodes;
const distance = (a, b) =>
  Math.hypot(nodes[a].x - nodes[b].x, nodes[a].y - nodes[b].y) *
  clubMap.units.scale_m_per_unit;
const neighbours = (() => {
  const graph = Object.fromEntries(Object.keys(nodes).map((k) => [k, []]));
  for (const [a, b] of clubMap.edges) {
    graph[a].push(b);
    graph[b].push(a);
  }
  return graph;
})();

export const nodeFor = (destination) =>
  nodes[destination] ? destination : clubMap.destinations[destination?.trim()];

// Nombre legible de un destino (códigos DEMO como RESTAURANT incluidos).
export const destinationLabel = (destination) =>
  nodes[nodeFor(destination)]?.label || destination;

function turn(prev, here, next) {
  const v1 = [here.x - prev.x, here.y - prev.y];
  const v2 = [next.x - here.x, next.y - here.y];
  const angle =
    (Math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]) *
      180) /
    Math.PI;
  if (Math.abs(angle) < 30) return "straight";
  if (Math.abs(angle) > 150) return "u_turn";
  return angle > 0 ? "right" : "left";
}

// Misma semántica que compute_route en Python (probado en tests/navigation.test.js).
export function computeRoute(category, destination, { escort = false } = {}) {
  const start = clubMap.start;
  const target = nodeFor(destination);
  if (!target)
    throw new Error(`Destino sin ubicación en el mapa: ${destination}`);
  const allowed = new Set(clubMap.access[category] || []);
  if (!allowed.has(nodes[target].zone))
    throw new Error("El destino está fuera de las zonas permitidas.");
  const prefs = clubMap.preferences?.[category] || {};
  const best = { [start]: 0 };
  const previous = {};
  const pending = [[0, start]];
  while (pending.length) {
    pending.sort((a, b) => a[0] - b[0]);
    const [cost, node] = pending.shift();
    if (node === target) break;
    if (cost > best[node]) continue;
    for (const next of neighbours[node]) {
      if (!allowed.has(nodes[next].zone)) continue;
      const step = distance(node, next) * (prefs[nodes[next].zone] ?? 1);
      if (cost + step < (best[next] ?? Infinity)) {
        best[next] = cost + step;
        previous[next] = node;
        pending.push([cost + step, next]);
      }
    }
  }
  if (target !== start && !previous[target])
    throw new Error("No existe un recorrido permitido hasta el destino.");
  const path = [target];
  while (path.at(-1) !== start) path.push(previous[path.at(-1)]);
  path.reverse();
  const meters = path
    .slice(1)
    .reduce((sum, node, i) => sum + distance(path[i], node), 0);
  const steps = [
    {
      node: start,
      action: "start",
      text: `Inicie en ${nodes[start].label} (${nodes[start].landmark}).`,
    },
  ];
  for (let i = 1; i < path.length; i += 1) {
    const here = nodes[path[i]];
    const leg = Math.round(distance(path[i - 1], path[i]));
    if (i === path.length - 1) {
      steps.push({
        node: path[i],
        action: "arrive",
        meters: leg,
        text: `Avance ${leg} m y llegará a ${here.label}: ${here.landmark}.`,
      });
      break;
    }
    const action = turn(nodes[path[i - 1]], here, nodes[path[i + 1]]);
    steps.push({
      node: path[i],
      action,
      meters: leg,
      text: `Avance ${leg} m hasta ${here.label} (${here.landmark}). ${turnText[action]}.`,
    });
  }
  let escortPoint = null;
  if (escort) {
    escortPoint = path.includes("recepcion_proveedores")
      ? "recepcion_proveedores"
      : path[Math.min(1, path.length - 1)];
    steps.splice(path.indexOf(escortPoint) + 1, 0, {
      node: escortPoint,
      action: "wait_escort",
      text: `Espere a su acompañante en ${nodes[escortPoint].label} antes de continuar.`,
    });
  }
  return {
    map_id: clubMap.id,
    simulated: clubMap.simulated,
    category,
    start,
    destination: target,
    destination_label: nodes[target].label,
    path,
    points: path.map((n) => [nodes[n].x, nodes[n].y]),
    distance_m: Math.round(meters),
    minutes: Math.max(
      1,
      Math.round(meters / clubMap.units.walking_speed_m_s / 60),
    ),
    steps,
    escort_point: escortPoint,
    note: notes[category] || "",
  };
}

// Ruta DEMO para el QR del celular: solo categoría y destino, sin identidad.
export const demoShareUrl = (route) =>
  `${location.origin}${location.pathname}#/ruta?demo=1&c=${encodeURIComponent(route.category)}&d=${encodeURIComponent(route.destination)}${route.escort_point ? "&e=1" : ""}`;

export function mapSvg(route, { compact = false, uid = "nav" } = {}) {
  const [x0, y0, w, h] = clubMap.viewBox;
  const allowed = new Set(clubMap.access[route?.category] || []);
  const onRoute = new Set(route?.path || []);
  const zoneColor = (zone) => clubMap.zones[zone]?.color || "#9ae6b4";
  const points = (route?.points || []).map((p) => p.join(",")).join(" ");
  const turns = (route?.steps || []).filter((s) =>
    ["left", "right", "u_turn", "wait_escort"].includes(s.action),
  );
  return `<svg class="nav-map ${compact ? "is-compact" : ""}" viewBox="${x0} ${y0} ${w} ${h}" role="img" aria-labelledby="${uid}-title ${uid}-desc">
    <title id="${uid}-title">${e(clubMap.title)}</title>
    <desc id="${uid}-desc">${route ? `Ruta desde ${e(nodes[route.start].label)} hasta ${e(route.destination_label)}: ${e(route.path.map((n) => nodes[n].label).join(", "))}.` : "Mapa del club"} ${e(clubMap.notice)}</desc>
    <defs>
      <pattern id="${uid}-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#1b7556" stroke-opacity=".06"/></pattern>
      <pattern id="${uid}-hatch" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0V12" stroke="#c2513d" stroke-opacity=".22" stroke-width="3"/></pattern>
      <filter id="${uid}-glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <linearGradient id="${uid}-route" x1="0" x2="1"><stop offset="0" stop-color="#1b7556"/><stop offset="1" stop-color="#b8955a"/></linearGradient>
    </defs>
    <rect x="${x0}" y="${y0}" width="${w}" height="${h}" rx="24" class="nav-ground"/>
    <rect x="${x0}" y="${y0}" width="${w}" height="${h}" rx="24" fill="url(#${uid}-grid)"/>
    ${clubMap.areas
      .map((a) => {
        const [ax, ay, aw, ah] = a.rect;
        const locked = route && !allowed.has(a.zone);
        return `<g class="nav-area ${locked ? "is-locked" : ""}"><rect x="${ax}" y="${ay}" width="${aw}" height="${ah}" rx="18" fill="${zoneColor(a.zone)}" fill-opacity="${locked ? 0.04 : 0.1}" stroke="${zoneColor(a.zone)}" stroke-opacity="${locked ? 0.3 : 0.45}"/>${locked ? `<rect x="${ax}" y="${ay}" width="${aw}" height="${ah}" rx="18" fill="url(#${uid}-hatch)"/>` : ""}<text x="${ax + 14}" y="${ay + 24}" class="nav-area-label">${e(a.label.toUpperCase())}${locked ? " · RESTRINGIDO" : ""}</text></g>`;
      })
      .join("")}
    <g class="nav-edges">${clubMap.edges
      .map(([a, b]) => {
        const usable =
          !route || (allowed.has(nodes[a].zone) && allowed.has(nodes[b].zone));
        return `<line x1="${nodes[a].x}" y1="${nodes[a].y}" x2="${nodes[b].x}" y2="${nodes[b].y}" class="${usable ? "" : "is-blocked"}"/>`;
      })
      .join("")}</g>
    ${
      route
        ? `<polyline points="${points}" class="nav-route-glow" filter="url(#${uid}-glow)"/>
    <polyline points="${points}" class="nav-route" stroke="url(#${uid}-route)" id="${uid}-path"/>
    <polyline points="${points}" class="nav-route-dash"/>
    <circle r="7" class="nav-traveller"><animateMotion dur="${Math.max(4, route.path.length * 1.2)}s" repeatCount="indefinite" path="M${points.replaceAll(" ", " L")}"/></circle>`
        : ""
    }
    <g class="nav-nodes">${Object.entries(nodes)
      .map(([key, n]) => {
        const hit = onRoute.has(key);
        const locked = route && !allowed.has(n.zone);
        const show = !compact || hit || n.kind === "destination";
        return `<g class="nav-node ${hit ? "on-route" : ""} ${locked ? "is-locked" : ""} kind-${n.kind}" transform="translate(${n.x} ${n.y})"><circle r="${hit ? 7 : 4.5}" fill="${zoneColor(n.zone)}"/>${show ? `<text y="${n.y > 600 ? -14 : 22}" text-anchor="middle">${e(n.label)}</text>` : ""}</g>`;
      })
      .join("")}</g>
    ${turns
      .map((s, i) => {
        const n = nodes[s.node];
        return `<g class="nav-turn ${s.action === "wait_escort" ? "is-escort" : ""}" transform="translate(${n.x + 16} ${n.y - 16})"><circle r="11"/><text y="4" text-anchor="middle">${s.action === "wait_escort" ? "!" : i + 1}</text></g>`;
      })
      .join("")}
    ${
      route
        ? `<g class="nav-start" transform="translate(${nodes[route.start].x} ${nodes[route.start].y})"><circle r="22" class="pulse"/><circle r="11"/><text y="4" text-anchor="middle">A</text></g>
    <g class="nav-dest" transform="translate(${nodes[route.destination].x} ${nodes[route.destination].y})"><circle r="26" class="pulse"/><circle r="13"/><text y="5" text-anchor="middle">B</text></g>`
        : ""
    }
    <text x="${x0 + w - 18}" y="${y0 + h - 16}" text-anchor="end" class="nav-sim-label">MAPA ESQUEMÁTICO · SIMULADO</text>
  </svg>`;
}

function stepsList(route) {
  return `<ol class="nav-steps">${route.steps
    .map(
      (s) =>
        `<li class="step-${e(s.action)}"><span class="nav-step-icon">${icon(stepIcon[s.action] || "move-up")}</span><div><strong>${e(s.action === "start" ? "Inicio" : s.action === "arrive" ? "Destino" : s.action === "wait_escort" ? "Acompañamiento" : turnText[s.action])}</strong><small>${e(s.text)}</small></div></li>`,
    )
    .join("")}</ol>`;
}

// Tarjeta completa: mapa, pasos y QR temporal para continuar en el celular.
export function routeCard(
  route,
  { qrId = "", title = "Su recorrido", compact = false } = {},
) {
  if (!route) return "";
  if (route.error)
    return `<section class="nav-card nav-error panel">${icon("alert-circle")}<p>No hay un recorrido permitido hasta ${e(route.destination || "el destino")}. Recepción le orientará.</p></section>`;
  return `<section class="nav-card" aria-label="Recorrido hasta ${e(route.destination_label)}">
    <header class="nav-card-head">
      <div><span class="eyebrow light">${icon("navigation")} ${e(title)}</span><h2>${e(route.destination_label)}</h2>
      <p>${e(route.note || "")}</p></div>
      <div class="nav-metrics"><span>${icon("footprints")}<strong>${route.distance_m} m</strong></span><span>${icon("clock-3")}<strong>${route.minutes} min</strong></span><span class="nav-cat">${e(categoryLabel[route.category] || route.category)}</span></div>
    </header>
    <div class="nav-body ${compact ? "is-compact" : ""}">
      <div class="nav-canvas">${mapSvg(route, { uid: `nav-${qrId || "map"}` })}</div>
      <aside class="nav-side">
        ${stepsList(route)}
        ${
          qrId
            ? `<div class="nav-qr"><canvas id="${e(qrId)}" aria-label="Código QR para ver la ruta en el celular"></canvas><div><strong>${icon("smartphone")} Continúe en su celular</strong><small>Escanee el código para llevar este recorrido. ${route.share_expires_at ? `Vence ${e(new Date(route.share_expires_at).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" }))}.` : "Ruta DEMO."} Solo muestra el camino: no concede permisos de acceso.</small></div></div>`
            : ""
        }
      </aside>
    </div>
    ${route.simulated ? `<p class="nav-notice">${icon("info")} ${e(clubMap.notice)}</p>` : ""}
  </section>`;
}

// En pantallas estrechas el mapa se desplaza: centra el recorrido visible.
export function revealRoutes(root = document) {
  root.querySelectorAll(".nav-canvas").forEach((canvas) => {
    const route = canvas.querySelector(".nav-route");
    if (!route || canvas.scrollWidth <= canvas.clientWidth + 4) return;
    const frame = canvas.getBoundingClientRect();
    const box = route.getBoundingClientRect();
    canvas.scrollLeft +=
      box.left + box.width / 2 - (frame.left + frame.width / 2);
  });
}

export const shareUrlFor = (route) =>
  route?.share_url || (route ? demoShareUrl(route) : "");

// Página pública #/ruta (celular del visitante). No requiere sesión.
export async function routePage(params, backendUrl) {
  let route = null,
    error = "";
  try {
    if (params.get("t")) {
      if (!backendUrl) throw new Error("Backend no configurado.");
      const response = await fetch(
        `${backendUrl}/navigation/shared/${encodeURIComponent(params.get("t"))}`,
        { cache: "no-store", signal: AbortSignal.timeout(10000) },
      );
      const json = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(json.detail || "La ruta no está disponible.");
      route = json.route;
      route.share_expires_at = json.expires_at;
    } else if (params.get("demo")) {
      route = computeRoute(params.get("c"), params.get("d"), {
        escort: params.get("e") === "1",
      });
    } else throw new Error("Falta el código de la ruta.");
  } catch (err) {
    error = err.message;
  }
  return `<main id="main" class="nav-page">
    <header class="nav-page-head"><span class="brand-mark">N<span>✦</span></span><div><span class="eyebrow light">Ruta personal</span><h1>Su camino, <em>trazado.</em></h1></div></header>
    ${route ? routeCard(route, { title: params.get("demo") ? "Recorrido DEMO" : "Su recorrido" }) : `<section class="nav-card nav-error">${icon("alert-circle")}<p>${e(error)}</p><p>Pida una nueva ruta en recepción.</p></section>`}
    <p class="nav-page-foot">${icon("shield-check")} Esta página solo muestra un recorrido. No es una credencial y no autoriza el ingreso.</p>
  </main>`;
}
