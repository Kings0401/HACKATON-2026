import { escape as e, timeLabel, dateLabel, today } from "./lib.js";
import { icon, badge } from "./ui.js";

const ROUTE_PREFIX =
  "M415 600 C 415 582 419 568 430 559 C 444 548 468 542 484 530 C 493 523 498 513 498 500";

const ROUTES = {
  reception: {
    label: "Recepción",
    area: "Bienvenida y acreditación",
    place: "Pabellón de recepción · acceso principal",
    minutes: "1 min",
    distance: "60 m",
    icon: "map-pin",
    point: [498, 500],
    path: ROUTE_PREFIX,
    steps: [
      [
        "Entrada principal",
        "Cruza el portón y sigue el camino de piedra entre los jardines.",
      ],
      [
        "Pérgola de bienvenida",
        "Avanza bajo la pérgola, junto al espejo de agua.",
      ],
      [
        "Recepción",
        "Valida tu credencial y recibe las indicaciones del equipo.",
      ],
    ],
  },
  "golf-1": {
    label: "Cancha 1",
    area: "Campo de golf · sector sur",
    place: "Salida sur · junto al parqueadero",
    minutes: "4 min",
    distance: "210 m",
    icon: "flag",
    point: [215, 435],
    path: `${ROUTE_PREFIX} C 470 490 440 480 405 470 C 370 460 330 455 295 450 C 260 445 235 440 215 435`,
    steps: [
      [
        "Entrada principal",
        "Ingresa y confirma tu llegada en el punto de bienvenida.",
      ],
      ["Recepción", "Valida tu credencial y toma el sendero sur."],
      ["Cancha 1", "Sigue la línea de árboles hasta la primera bandera."],
    ],
  },
  "golf-2": {
    label: "Cancha 2",
    area: "Campo de golf · orilla del lago",
    place: "Sendero oeste · mirador del lago",
    minutes: "5 min",
    distance: "300 m",
    icon: "flag",
    point: [250, 200],
    path: `${ROUTE_PREFIX} C 480 487 450 472 418 458 C 386 444 352 432 322 420 C 292 408 274 392 265 368 C 256 344 258 316 266 291 C 274 266 282 246 276 226 C 272 213 262 205 250 200`,
    steps: [
      ["Entrada principal", "Ingresa y confirma tu llegada en el pabellón."],
      [
        "Recepción",
        "Valida tu credencial y bordea el lago por el sendero oeste.",
      ],
      ["Cancha 2", "La bandera aparece al norte, junto al mirador del lago."],
    ],
  },
  "golf-3": {
    label: "Cancha 3",
    area: "Campo de golf · bosque oeste",
    place: "Sendero de las magnolias",
    minutes: "6 min",
    distance: "360 m",
    icon: "flag",
    point: [120, 210],
    path: `${ROUTE_PREFIX} C 474 488 438 474 402 462 C 366 450 326 440 292 424 C 254 406 218 382 188 352 C 158 322 140 278 130 247 C 125 232 123 220 120 210`,
    steps: [
      ["Entrada principal", "Ingresa y confirma tu llegada en el pabellón."],
      [
        "Recepción",
        "Valida tu credencial y sigue el sendero de las magnolias.",
      ],
      ["Cancha 3", "El bosque oeste abre paso a la tercera bandera."],
    ],
  },
  "golf-4": {
    label: "Cancha 4",
    area: "Campo de golf · sector norte",
    place: "Sendero de la colina",
    minutes: "7 min",
    distance: "420 m",
    icon: "flag",
    point: [435, 135],
    path: `${ROUTE_PREFIX} C 500 470 500 442 498 418 C 496 392 490 368 482 344 C 474 318 466 292 458 262 C 450 232 440 190 435 135`,
    steps: [
      ["Entrada principal", "Ingresa y confirma tu llegada en el pabellón."],
      ["Recepción", "Valida tu credencial y toma el sendero de la colina."],
      ["Cancha 4", "Asciende suavemente hasta la bandera norte."],
    ],
  },
  "golf-5": {
    label: "Cancha 5",
    area: "Campo de golf · sector lago",
    place: "Sendero este · jardín de los robles",
    minutes: "5 min",
    distance: "310 m",
    icon: "flag",
    point: [482, 300],
    path: `${ROUTE_PREFIX} C 500 470 502 446 500 422 C 498 396 494 372 490 348 C 487 328 484 312 482 300`,
    steps: [
      ["Entrada principal", "Ingresa y confirma tu llegada en el pabellón."],
      [
        "Recepción",
        "Valida tu credencial y avanza por el jardín de los robles.",
      ],
      ["Cancha 5", "La bandera espera junto al extremo este del lago."],
    ],
  },
  restaurant: {
    label: "Restaurante",
    area: "Casa club · ala este",
    place: "Terraza de temporada",
    minutes: "4 min",
    distance: "240 m",
    icon: "utensils",
    point: [802, 430],
    path: `${ROUTE_PREFIX} C 530 502 570 506 610 511 C 650 516 700 513 740 501 C 765 494 782 476 794 454 C 799 444 801 437 802 430`,
    steps: [
      ["Entrada principal", "Ingresa y confirma tu llegada en el pabellón."],
      ["Recepción", "Valida tu credencial y rodea la casa club por el jardín."],
      [
        "Restaurante N Club",
        "Sube a la terraza; el equipo de sala te recibirá en tu mesa.",
      ],
    ],
  },
  lounge: {
    label: "Lounge VIP",
    area: "Pabellón privado · nivel superior",
    place: "Acceso Black VIP · terraza de socios",
    minutes: "6 min",
    distance: "340 m",
    icon: "crown",
    point: [790, 282],
    vipOnly: true,
    path: `${ROUTE_PREFIX} C 535 505 590 520 650 525 C 700 530 738 520 752 495 C 766 470 753 445 744 420 C 735 395 733 365 743 340 C 753 316 772 296 790 282`,
    steps: [
      ["Entrada principal", "Ingresa y confirma tu llegada en el pabellón."],
      [
        "Recepción",
        "Valida tu credencial; nuestro equipo te reconocerá como socio Black.",
      ],
      [
        "Lounge VIP",
        "El pabellón privado se eleva sobre la terraza este de la casa club.",
      ],
    ],
  },
};

const SERVICE_ROUTE_FALLBACK = {
  golf: "golf-1",
  restaurant: "restaurant",
  lounge: "lounge",
};

function allowedRoute(key, p) {
  return Boolean(ROUTES[key] && (!ROUTES[key].vipOnly || p?.role === "VIP"));
}

function nextReservation(p, data) {
  return (
    data.reservations
      .filter(
        (r) =>
          r.user_id === p.id &&
          r.status === "confirmed" &&
          r.reservation_date >= today(),
      )
      .sort((a, b) =>
        (a.reservation_date + a.start_time).localeCompare(
          b.reservation_date + b.start_time,
        ),
      )[0] || null
  );
}

function routeForService(serviceId, data) {
  if (!serviceId) return null;
  if (ROUTES[serviceId] && serviceId !== "reception") return serviceId;
  const service = data.services.find((s) => s.id === serviceId);
  if (!service) return null;
  if (service.category === "golf") {
    const hole = String(service.name || "").match(/(\d+)/)?.[1];
    return hole && Number(hole) >= 1 && Number(hole) <= 5
      ? `golf-${hole}`
      : SERVICE_ROUTE_FALLBACK.golf;
  }
  return SERVICE_ROUTE_FALLBACK[service.category] || null;
}

function defaultRoute(p, data, params) {
  const suggested = params?.get("to");
  if (suggested && allowedRoute(suggested, p)) return suggested;
  const upcoming = nextReservation(p, data);
  const bookingRoute = upcoming
    ? routeForService(upcoming.service_id, data)
    : null;
  if (bookingRoute && allowedRoute(bookingRoute, p)) return bookingRoute;
  return "reception";
}

function fairway(d) {
  return `<path class="map-fairway" d="${d}" /><path class="map-fairway-core" d="${d}" />`;
}

function tree(x, y, r) {
  return `<circle class="map-tree" cx="${x}" cy="${y}" r="${r}" /><circle class="map-tree-light" cx="${x - r * 0.25}" cy="${y - r * 0.3}" r="${r * 0.42}" />`;
}

function hole(x, y, n) {
  return `<g class="map-hole" transform="translate(${x} ${y})">
    <circle class="map-green" r="17" />
    <circle class="map-green-core" r="10" />
    <path class="map-flag-pole" d="M9 -26 L9 0" />
    <path class="map-flag" d="M9 -26 L23 -21 L9 -15 Z" />
    <text class="map-hole-num" x="0" y="5" text-anchor="middle">${n}</text>
  </g>`;
}

function routeGroup(key, active) {
  const route = ROUTES[key];
  const [x, y] = route.point;
  return `<g class="map-route ${key === active ? "is-active" : ""}" data-map-route="${key}">
    <path class="map-route-base" d="${route.path}" />
    <path class="map-route-glow" d="${route.path}" />
    <path class="map-route-line" id="cm-path-${key}" d="${route.path}" />
    <circle class="map-traveller" r="4.5" aria-hidden="true">
      <animateMotion dur="7s" repeatCount="indefinite">
        <mpath href="#cm-path-${key}" />
      </animateMotion>
    </circle>
    <g class="map-dest" transform="translate(${x} ${y})">
      <circle class="map-dest-halo" r="19" />
      <circle class="map-dest-ring" r="9" />
      <circle class="map-dest-core" r="4" />
    </g>
  </g>`;
}

function mapSvg(p, active, compact = false) {
  const titleId = compact ? "cm-preview-title" : "cm-map-title";
  const descId = compact ? "cm-preview-desc" : "cm-map-desc";
  const route = ROUTES[active];
  const routeKeys = Object.keys(ROUTES).filter((key) => allowedRoute(key, p));
  return `<svg class="club-map-svg ${compact ? "is-compact" : ""}" viewBox="${compact ? "90 90 790 545" : "0 0 960 640"}" role="img" aria-labelledby="${titleId} ${descId}" preserveAspectRatio="${compact ? "xMidYMid slice" : "xMidYMid meet"}">
    <title id="${titleId}">Mapa ilustrativo de N Club World</title>
    <desc id="${descId}" data-map-desc>Plano del club con la entrada principal, recepción, casa club, restaurante, lounge VIP, lago y cinco canchas. La ruta activa lleva a ${e(route.label)}.</desc>
    <defs>
      <linearGradient id="cm-paper" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#f2f0e5" />
        <stop offset=".58" stop-color="#edecdf" />
        <stop offset="1" stop-color="#e7eadc" />
      </linearGradient>
      <linearGradient id="cm-water" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#cbdcd8" />
        <stop offset="1" stop-color="#aec9c4" />
      </linearGradient>
      <linearGradient id="cm-roof" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#466353" />
        <stop offset="1" stop-color="#2f4c3e" />
      </linearGradient>
      <pattern id="cm-dots" width="22" height="22" patternUnits="userSpaceOnUse">
        <circle cx="2" cy="2" r="1" fill="#284538" opacity=".12" />
      </pattern>
      <filter id="cm-soft" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="7" stdDeviation="8" flood-color="#102c24" flood-opacity=".13" />
      </filter>
    </defs>
    <rect width="960" height="640" rx="20" fill="url(#cm-paper)" />
    <rect width="960" height="640" rx="20" fill="url(#cm-dots)" />
    <g class="map-contours" aria-hidden="true">
      <path d="M-40 150 C 100 80 230 125 345 45 C 400 6 450 0 520 18" />
      <path d="M-30 205 C 95 140 225 180 350 100 C 415 58 470 50 545 68" />
      <path d="M510 610 C 620 590 705 560 810 585 C 875 600 925 620 990 600" />
      <path d="M80 640 C 170 600 260 610 330 575" />
    </g>
    <g class="map-fairways" aria-hidden="true">
      ${fairway("M120 480 C 155 462 190 448 225 438")}
      ${fairway("M185 285 C 215 260 232 230 246 198")}
      ${fairway("M62 280 C 88 262 104 238 116 206")}
      ${fairway("M355 190 C 388 165 414 138 430 115")}
      ${fairway("M375 345 C 418 330 452 304 477 276")}
    </g>
    <text class="map-label map-label--tiny map-label--detail" x="70" y="56">THE GOLF COURSE</text>
    <text class="map-label map-label--field" x="68" y="90">Campo de golf</text>
    <g class="map-water" aria-hidden="true">
      <path class="map-lake" d="M300 302 C 315 278 350 272 382 285 C 410 297 423 325 410 350 C 396 378 360 392 328 382 C 298 372 282 342 300 302 Z" />
      <path class="map-wave" d="M313 316 C 330 305 352 305 368 315 C 383 324 397 324 407 318" />
      <path class="map-wave" d="M310 340 C 330 331 350 331 368 340 C 384 348 396 348 406 343" />
      <path class="map-wave" d="M321 360 C 337 354 354 354 369 361" />
      <text class="map-label map-label--lake" x="356" y="326" text-anchor="middle">Lago</text>
    </g>
    <g class="map-parking" aria-hidden="true">
      <rect x="58" y="505" width="154" height="94" rx="12" />
      <path d="M88 520 V 584 M118 520 V 584 M148 520 V 584 M178 520 V 584" class="map-parking-line" />
      <text class="map-label map-label--tiny map-label--detail" x="135" y="550" text-anchor="middle">PARQUEADERO</text>
    </g>
    <path class="map-drive" d="M290 640 C 345 616 380 604 415 600 C 452 598 486 612 540 640" />
    <path class="map-path" d="M415 600 C 415 570 450 545 498 525 C 520 516 534 508 540 500" />
    <path class="map-path" d="M498 500 C 558 492 618 482 678 468 C 738 454 790 448 830 440" />
    <path class="map-path" d="M498 500 C 460 480 420 462 380 450 C 330 435 280 430 230 425" />
    <path class="map-path" d="M498 500 C 505 460 505 420 500 380" />
    <g class="map-buildings">
      <g class="map-zone map-zone--reception" filter="url(#cm-soft)">
        <rect class="map-building" x="350" y="458" width="132" height="82" rx="11" />
        <path class="map-roof" d="M350 469 Q 416 438 482 469 V 479 H 350 Z" />
        <rect class="map-window" x="364" y="492" width="104" height="34" rx="4" />
        <text class="map-label map-label--zone" x="416" y="508" text-anchor="middle">Recepción</text>
        <text class="map-label map-label--tiny map-label--detail" x="416" y="523" text-anchor="middle">BIENVENIDA</text>
      </g>
      <g class="map-zone map-zone--clubhouse" filter="url(#cm-soft)">
        <rect class="map-building" x="546" y="310" width="192" height="120" rx="12" />
        <path class="map-roof" d="M546 326 L 738 310 V 330 L 546 346 Z" />
        <rect class="map-window" x="568" y="356" width="58" height="48" rx="4" />
        <rect class="map-window" x="638" y="356" width="42" height="48" rx="4" />
        <rect class="map-window" x="690" y="356" width="30" height="48" rx="4" />
        <text class="map-label map-label--serif" x="642" y="376" text-anchor="middle">Casa club</text>
        <text class="map-label map-label--tiny map-label--detail" x="642" y="393" text-anchor="middle">HOSPITALIDAD · MEMBERS ONLY</text>
      </g>
      <g class="map-zone map-zone--restaurant" filter="url(#cm-soft)">
        <rect class="map-building" x="760" y="330" width="145" height="98" rx="10" />
        <path class="map-roof" d="M760 342 L 905 330 V 348 L 760 360 Z" />
        <rect class="map-window" x="778" y="370" width="109" height="32" rx="4" />
        <text class="map-label map-label--serif" x="832" y="383" text-anchor="middle">Restaurante</text>
        <text class="map-label map-label--tiny map-label--detail" x="832" y="397" text-anchor="middle">FINE DINING</text>
      </g>
      <g class="map-zone map-zone--lounge" filter="url(#cm-soft)">
        <rect class="map-building map-building--vip" x="720" y="200" width="150" height="78" rx="10" />
        <path class="map-roof map-roof--vip" d="M720 212 L 870 200 V 218 L 720 230 Z" />
        <rect class="map-window" x="738" y="238" width="114" height="22" rx="4" />
        <circle class="map-vip-mark" cx="852" cy="211" r="4" />
        <text class="map-label map-label--serif" x="795" y="240" text-anchor="middle">Lounge VIP</text>
        <text class="map-label map-label--tiny map-label--detail" x="795" y="254" text-anchor="middle">BLACK MEMBERS</text>
        <g class="map-terrace" aria-hidden="true">
          <path d="M730 278 V 298 M750 278 V 298 M770 278 V 298 M790 278 V 298" />
          <path d="M726 306 H 812" />
          <circle cx="738" cy="312" r="3" /><circle cx="770" cy="312" r="3" /><circle cx="802" cy="312" r="3" />
        </g>
      </g>
      <g class="map-zone map-zone--service" filter="url(#cm-soft)">
        <rect class="map-building map-building--service" x="838" y="520" width="86" height="64" rx="8" />
        <text class="map-label map-label--tiny map-label--detail" x="881" y="548" text-anchor="middle">SERVICIO</text>
      </g>
    </g>
    <g class="map-greens" aria-hidden="true">
      ${hole(215, 435, 1)}
      ${hole(250, 200, 2)}
      ${hole(120, 210, 3)}
      ${hole(435, 135, 4)}
      ${hole(482, 300, 5)}
    </g>
    <g class="map-trees" aria-hidden="true">
      ${[
        [42, 140, 17],
        [70, 166, 13],
        [32, 198, 12],
        [190, 42, 14],
        [516, 78, 17],
        [558, 116, 11],
        [618, 78, 14],
        [900, 78, 13],
        [932, 158, 19],
        [938, 236, 12],
        [892, 300, 13],
        [500, 250, 9],
        [520, 462, 10],
        [744, 572, 12],
        [286, 566, 13],
        [250, 610, 9],
        [60, 468, 11],
        [482, 128, 11],
        [520, 168, 9],
        [690, 600, 8],
      ]
        .map(([x, y, r]) => tree(x, y, r))
        .join("")}
    </g>
    <g class="map-gate" aria-hidden="true">
      <rect x="386" y="594" width="8" height="20" rx="2" />
      <rect x="436" y="594" width="8" height="20" rx="2" />
    </g>
    <path class="map-gate-line" d="M394 602 H 436" />
    <text class="map-label map-label--tiny map-label--entrance" x="415" y="630" text-anchor="middle">ENTRADA PRINCIPAL</text>
    <g class="map-routes">
      ${routeKeys.map((key) => routeGroup(key, active)).join("")}
    </g>
    <g class="map-start" aria-hidden="true">
      <circle class="map-start-halo" cx="415" cy="600" r="17" />
      <circle class="map-start-ring" cx="415" cy="600" r="9" />
      <circle class="map-start-dot" cx="415" cy="600" r="4" />
    </g>
    <g class="map-stop" aria-hidden="true">
      <circle cx="498" cy="500" r="8" />
      <circle cx="498" cy="500" r="3" />
    </g>
    <g class="map-compass" aria-hidden="true" transform="translate(900 72)">
      <circle r="27" />
      <path class="map-compass-needle" d="M0 -15 L 6 7 L 0 3 L -6 7 Z" />
      <text class="map-label map-label--tiny" x="0" y="-34" text-anchor="middle">N</text>
    </g>
  </svg>`;
}

function routePanel(p, data, key, active, upcoming, upcomingKey) {
  const route = ROUTES[key];
  const isNext = key === upcomingKey;
  return `<div class="map-route-panel" data-map-panel="${key}" ${key === active ? "" : "hidden"}>
    <div class="map-route-top">
      <span class="eyebrow">TU RUTA</span>
      <span class="map-route-badge">${icon("clock-3")} Aprox. ${route.minutes}</span>
    </div>
    <h2>${e(route.label)}</h2>
    <p class="map-route-place">${e(route.area)} · ${e(route.place)}</p>
    ${
      isNext && upcoming
        ? `<p class="map-route-reservation">${icon("calendar-check")} <span>Tu próxima experiencia · ${dateLabel(upcoming.reservation_date)} · ${timeLabel(upcoming.start_time)}</span></p>`
        : ""
    }
    <div class="map-route-stats">
      <span>${icon("map-pin")} ${e(route.distance)}</span>
      <span>${icon("clock-3")} ${e(route.minutes)} a pie</span>
    </div>
    <ol class="map-steps">
      ${route.steps
        .map(
          ([title, text], i) =>
            `<li><span>${i + 1}</span><div><strong>${e(title)}</strong><small>${e(text)}</small></div></li>`,
        )
        .join("")}
    </ol>
    <div class="map-route-actions">
      <a class="button primary full" href="#/credential">${icon("qr-code")} Ver mi credencial</a>
      <a class="text-link" href="#/bookings?tab=mine">Mis reservas ${icon("arrow-up-right")}</a>
    </div>
  </div>`;
}

function destinationButton(key, active, upcomingKey) {
  const route = ROUTES[key];
  return `<button type="button" class="map-destination ${key === active ? "is-active" : ""}" data-action="map-destination" data-destination="${key}" aria-pressed="${key === active}">
    <span class="map-destination-icon">${icon(route.icon)}</span>
    <span class="map-destination-copy"><strong>${e(route.label)}</strong><small>${key === upcomingKey ? "Tu próxima experiencia" : `${e(route.minutes)} · ${e(route.distance)}`}</small></span>
  </button>`;
}

function destinationList(p, data, active, upcoming, upcomingKey) {
  const order = [];
  if (upcomingKey) order.push(upcomingKey);
  order.push("reception", "restaurant", "lounge");
  for (let i = 1; i <= 5; i += 1) order.push(`golf-${i}`);
  return [...new Set(order)].filter((key) => ROUTES[key]);
}

export function clubMapPage(p, data, params) {
  const upcoming = nextReservation(p, data);
  const upcomingKey = upcoming
    ? routeForService(upcoming.service_id, data)
    : null;
  const active = defaultRoute(p, data, params);
  const route = ROUTES[active];
  const order = destinationList(p, data, active, upcoming, upcomingKey);
  const accessible = order.filter((key) => allowedRoute(key, p));
  return `<div class="club-map-page" data-club-map>
    <div class="page-heading map-page-heading">
      <div>
        <span class="eyebrow">MAPA DEL CLUB</span>
        <h1>Tu camino, <em>trazado.</em></h1>
        <p>Del acceso principal a tu próxima experiencia. Una guía serena para moverte por el club.</p>
      </div>
      ${badge(p.role)}
    </div>
    <div class="map-layout">
      <section class="map-card">
        <div class="map-card-head">
          <div>
            <span class="eyebrow">N CLUB WORLD · SITE PLAN</span>
            <h2>El club, de un vistazo.</h2>
          </div>
          <span class="map-active-pill">${icon("map-pin")} Ruta a <strong data-map-pill-name>${e(route.label)}</strong><small data-map-pill-time>${e(route.minutes)} · ${e(route.distance)}</small></span>
        </div>
        <div class="map-canvas">
          ${mapSvg(p, active)}
        </div>
        <div class="map-legend" aria-hidden="true">
          <span><i class="map-legend-line"></i>Tu ruta</span>
          <span><i class="map-legend-start"></i>Entrada</span>
          <span><i class="map-legend-vip"></i>Zona VIP</span>
        </div>
        <p class="map-caption">${icon("info")} Mapa ilustrativo. La ruta comienza en la entrada principal y es una referencia; el equipo de recepción siempre puede acompañarte.</p>
      </section>
      <aside class="map-side">
        <section class="map-route-card">
          ${accessible
            .map((key) =>
              routePanel(p, data, key, active, upcoming, upcomingKey),
            )
            .join("")}
          <p class="sr-only" aria-live="polite" data-map-live></p>
        </section>
        <section class="map-destinations-card">
          <div class="map-destinations-head">
            <div>
              <span class="eyebrow">ELIGE TU DESTINO</span>
              <h2>¿A dónde vamos?</h2>
            </div>
          </div>
          <div class="map-destination-grid" role="group" aria-label="Elige tu destino">
            ${order
              .map((key) =>
                allowedRoute(key, p)
                  ? destinationButton(key, active, upcomingKey)
                  : `<span class="map-destination is-locked" aria-disabled="true"><span class="map-destination-icon">${icon("lock-keyhole")}</span><span class="map-destination-copy"><strong>Lounge VIP</strong><small>Exclusivo Black VIP</small></span></span>`,
              )
              .join("")}
          </div>
          <p class="map-destination-note">${icon("shield-check")} Los destinos se ajustan a tu categoría de membresía.</p>
        </section>
      </aside>
    </div>
  </div>`;
}

export function clubMapBanner(p, data) {
  const upcoming = nextReservation(p, data);
  const bookingRoute = upcoming
    ? routeForService(upcoming.service_id, data)
    : null;
  const active =
    bookingRoute && allowedRoute(bookingRoute, p) ? bookingRoute : "reception";
  const route = ROUTES[active];
  return `<a class="map-banner" href="#/map" aria-label="Abrir el mapa del club${upcoming ? `, ruta a ${route.label}` : ""}">
    <span class="map-banner-copy">
      <span class="eyebrow light">MAPA DEL CLUB</span>
      <span class="map-banner-title">Tu camino, <em>trazado.</em></span>
      <span class="map-banner-text">${upcoming ? `Ruta a ${e(route.label)} · ${e(route.minutes)} a pie desde la entrada principal.` : "Explora el club y traza tu ruta desde la entrada principal."}</span>
      <span class="map-banner-link">Abrir el mapa ${icon("arrow-up-right")}</span>
    </span>
    <span class="map-banner-visual" aria-hidden="true">
      ${mapSvg(p, active, true)}
      <span class="map-banner-pin">${icon("map-pin")} ${e(route.label)}</span>
    </span>
  </a>`;
}

export function revealMapRoute() {
  const page = document.querySelector("[data-club-map]");
  const canvas = page?.querySelector(".map-canvas");
  const marker = page?.querySelector(".map-route.is-active .map-dest");
  if (!canvas || !marker || canvas.scrollWidth <= canvas.clientWidth + 4)
    return;
  const frame = canvas.getBoundingClientRect();
  const point = marker.getBoundingClientRect();
  canvas.scrollLeft = Math.max(
    0,
    canvas.scrollLeft +
      (point.left + point.width / 2) -
      (frame.left + frame.width / 2),
  );
}

export function selectMapDestination(key) {
  const page = document.querySelector("[data-club-map]");
  if (!page || !ROUTES[key]) return;
  const selected = page.querySelector(
    `[data-action="map-destination"][data-destination="${key}"]`,
  );
  if (!selected) return;
  page.querySelectorAll("[data-action='map-destination']").forEach((button) => {
    const active = button.dataset.destination === key;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  page.querySelectorAll("[data-map-route]").forEach((group) => {
    group.classList.toggle("is-active", group.dataset.mapRoute === key);
  });
  page.querySelectorAll("[data-map-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.mapPanel !== key;
  });
  const route = ROUTES[key];
  const name = page.querySelector("[data-map-pill-name]");
  const time = page.querySelector("[data-map-pill-time]");
  const desc = page.querySelector("[data-map-desc]");
  const live = page.querySelector("[data-map-live]");
  if (name) name.textContent = route.label;
  if (time) time.textContent = `${route.minutes} · ${route.distance}`;
  if (desc)
    desc.textContent = `Plano del club con la entrada principal, recepción, casa club, restaurante, lounge VIP, lago y cinco canchas. La ruta activa lleva a ${route.label}.`;
  if (live)
    live.textContent = `Ruta a ${route.label} actualizada. ${route.minutes} a pie desde la entrada principal.`;
  requestAnimationFrame(() => {
    revealMapRoute();
  });
  try {
    history.replaceState(null, "", `#/map?to=${encodeURIComponent(key)}`);
  } catch {
    /* The route still updates if the browser restricts history updates. */
  }
}
