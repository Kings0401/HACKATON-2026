import { icon, brand, badge, status, membershipCard, empty } from "./ui.js";
import {
  escape as e,
  roles,
  today,
  dateAfter,
  dateLabel,
  timeLabel,
  clockLabel,
  isMember,
  images,
  canBook,
  canUseApp,
} from "./lib.js";
import { sessionState } from "./data.js";
import { configured, demoEnabled, backendUrl } from "./config.js";
import { demoPeople } from "./demo.js";
import { clubMapBanner } from "./clubmap.js";
import { routeCard } from "./navigation.js";

const link = (route, label, ico, active) =>
  `<a href="#/${route}" class="nav-item ${active === route ? "active" : ""}" ${active === route ? 'aria-current="page"' : ""}>${icon(ico)}<span>${label}</span>${icon("chevron-right", "nav-chevron")}</a>`;
export function landing() {
  return /* HTML */ `<div class="landing">
    <header class="landing-nav">
      ${brand(true)}
      <nav aria-label="Navegación principal">
        <a href="#/">Inicio</a><a href="#/memberships">Membresías</a
        ><a href="#/experiences">Experiencias</a
        ><a href="#/bookings">Reservas</a>
      </nav>
      <a class="nav-access" href="#/login"
        >${icon("user-round")}<span>Mi club</span>${icon("arrow-up-right")}</a
      >
      <details class="mobile-menu">
        <summary aria-label="Menú de navegación">
          ${icon("menu")}${icon("x")}
        </summary>
        <nav aria-label="Menú del club">
          <a href="#/">Inicio ${icon("arrow-up-right")}</a>
          <a href="#/memberships">Membresías ${icon("gem")}</a>
          <a href="#/experiences">Experiencias ${icon("sparkles")}</a>
          <a href="#/login">Ingresar al club ${icon("arrow-right")}</a>
        </nav>
      </details>
    </header>
    <main id="main">
      <section class="landing-hero">
        <img
          class="hero-image"
          src="${images.golf}"
          alt="Campo de golf rodeado de naturaleza al atardecer"
          fetchpriority="high"
        />
        <div class="hero-shade"></div>
        <div class="hero-copy">
          <div class="eyebrow light">
            <span></span> A WORLD BEYOND THE ORDINARY
          </div>
          <h1>Tu club.<br />A tu <em>manera.</em></h1>
          <p>
            Una nueva dimensión de exclusividad,<br class="desktop-break" />
            experiencias y hospitalidad inteligente.
          </p>
          <div class="hero-actions">
            <a class="button gold" href="#/login"
              >Entrar a mi club ${icon("arrow-up-right")}</a
            ><a class="button glass" href="#/experiences"
              >Explorar experiencias ${icon("arrow-right")}</a
            >
          </div>
          <div class="hero-note">
            ${icon("leaf")} Excepcional por naturaleza. Exclusivo por elección.
          </div>
        </div>
        <div class="hero-footer">
          <span>01 <span class="hero-line"></span> 03</span
          ><a href="#/experiences"
            >DESCUBRE TU PRÓXIMA EXPERIENCIA ${icon("arrow-down-right")}</a
          ><span>EST. 2026 · COLOMBIA</span>
        </div>
        <div class="vertical-note">THE ART OF BELONGING</div>
      </section>
      <section class="landing-intro">
        <span class="eyebrow">BIENVENIDO A TU MUNDO</span>
        <h2>
          Hay lugares que visitas.<br /><em>Y lugares a los que perteneces.</em>
        </h2>
        <p>
          La pasión por el golf, el placer de una buena mesa y una atención que
          se anticipa a ti. Todo, en un solo lugar.
        </p>
        <div class="intro-features">
          <a href="#/experiences"
            >${icon("flag")}<span
              >Golf extraordinario<small
                >Cinco canchas. Infinitas posibilidades.</small
              ></span
            >${icon("arrow-up-right")}</a
          ><a href="#/memberships"
            >${icon("gem")}<span
              >El privilegio de pertenecer<small
                >Una membresía a tu altura.</small
              ></span
            >${icon("arrow-up-right")}</a
          ><a href="#/login"
            >${icon("heart-handshake")}<span
              >Hospitalidad inteligente<small
                >Tu experiencia, siempre personal.</small
              ></span
            >${icon("arrow-up-right")}</a
          >
        </div>
      </section>
    </main>
    <footer class="landing-bottom">
      ${brand()}
      <p>N Club World — The Future of Exclusive Hospitality</p>
      <span>© ${new Date().getFullYear()} N Club World</span>
    </footer>
  </div>`;
}

export function loginPage(showDemo = false) {
  return /* HTML */ `<div class="auth-layout">
    <aside class="auth-photo">
      <img src="${images.golf}" alt="Paisaje del campo de golf" />
      <div class="auth-photo-shade"></div>
      ${brand(true)}
      <div>
        <span class="eyebrow light">TU MUNDO TE ESPERA</span>
        <h1>El placer de<br /><em>volver a casa.</em></h1>
        <p>Un lugar excepcional. Una experiencia que es tuya.</p>
      </div>
      <small>N CLUB WORLD · PRIVATE MEMBERS CLUB</small>
    </aside>
    <main id="main" class="auth-main">
      <a class="back-link" href="#/">${icon("arrow-left")} Volver al club</a>
      <div class="auth-box">
        <div class="mobile-brand">${brand()}</div>
        <span class="eyebrow">THE ART OF BELONGING</span>
        <h1>Bienvenido a tu club.</h1>
        <p>Ingresa para reservar y tener tu credencial a mano.</p>
        <div class="auth-tabs">
          <a href="#/login" class="${!showDemo ? "active" : ""}">Mi membresía</a
          >${demoEnabled ? `<a href="#/demo" class="${showDemo ? "active" : ""}">Explorar demo <span>DEMO</span></a>` : ""}
        </div>
        ${
          showDemo
            ? `<div class="demo-disclaimer">${icon("info")}<span>Elige un perfil para conocer la app. Son datos de prueba y no permiten entrar al club.</span></div><div class="demo-profiles">${demoPeople
                .filter(([role]) => canUseApp({ role }))
                .map(
                  ([role, first, last]) =>
                    `<button class="demo-profile" data-action="demo-login" data-id="demo-${role.toLowerCase()}"><span class="avatar role-${role.toLowerCase()}">${first[0]}${last[0]}</span><span><strong>${first} ${last}</strong><small>${roles[role]}</small></span>${icon("arrow-up-right")}</button>`,
                )
                .join("")}</div>`
            : `<form id="login-form"><label>Correo electrónico<span class="input-wrap">${icon("mail")}<input type="email" name="email" autocomplete="username" inputmode="email" autocapitalize="none" spellcheck="false" placeholder="tu@correo.com" required maxlength="254"/></span></label><label>Contraseña<span class="input-wrap">${icon("lock-keyhole")}<input type="password" name="password" autocomplete="current-password" placeholder="Tu contraseña" required minlength="6" maxlength="200"/><button type="button" data-action="toggle-password" class="inline-icon" aria-label="Mostrar contraseña">${icon("eye")}</button></span></label><p id="form-error" class="form-error" role="alert"></p><button class="button primary full" type="submit">Iniciar sesión ${icon("arrow-right")}</button></form>${!configured ? '<p class="setup-note">Puedes conocer la app en Explorar demo.</p>' : ""}<p class="auth-help">¿Necesitas ayuda con tu cuenta?<br>Contacta al equipo de recepción de tu club.</p>`
        }
        <p class="visitor-help">
          ¿Vienes como invitado, personal o proveedor? Recepción gestiona tu
          ingreso. No necesitas una cuenta en la app.
        </p>
        <div class="secure-note">
          ${icon("shield-check")} Tu privacidad es parte de nuestra
          hospitalidad.
        </div>
      </div>
      <small class="auth-copyright"
        >N Club World — Extraordinary by nature.</small
      >
    </main>
  </div>`;
}

export function shell(content, route, p) {
  const admin = p.role === "ADMIN" && p.membership_status === "active";
  const member = isMember(p);
  const nav = admin
    ? [
        ["admin", "Vista general", "layout-dashboard"],
        ["admin/users", "Personas", "users"],
        ["admin/reservations", "Reservas", "calendar-days"],
        ["admin/invitations", "Invitaciones", "ticket"],
        ["admin/work", "Turnos y órdenes", "briefcase-business"],
        ["admin/access", "Registro de accesos", "activity"],
        ["admin/robots", "Seguimiento de robots", "bot"],
        ["reception", "Recepción", "bot"],
      ]
    : [
        ["dashboard", "Inicio", "layout-dashboard"],
        ...(member
          ? [
              ["bookings", "Reservar", "calendar-days"],
              ["map", "Mapa del club", "map-pin"],
              ["experiences", "Experiencias", "sparkles"],
            ]
          : []),
        ["credential", "Mi credencial", "qr-code"],
        ["history", "Mis visitas", "history"],
      ];
  nav.push(["profile", "Mi perfil", "user-round"]);
  return /* HTML */ `<div
    class="app-layout ${p.role === "VIP" ? "vip-theme" : ""}"
  >
    <aside class="sidebar">
      ${brand()}
      <div class="sidebar-section">
        ${admin ? "CLUB MANAGEMENT" : "TU ESPACIO PERSONAL"}
      </div>
      <nav aria-label="Navegación del panel">
        ${nav.map((n) => link(...n, route)).join("")}
      </nav>
      <div class="sidebar-bottom">
        <div class="sidebar-concierge">
          ${icon("heart-handshake")}<span
            >Siempre a tu disposición<small
              >El arte de la hospitalidad</small
            ></span
          >
        </div>
        <button class="nav-item" data-action="logout">
          ${icon("log-out")} Cerrar sesión</button
        ><small>PRIVATE MEMBERS CLUB · EST. 2026</small>
      </div>
    </aside>
    <div class="app-body">
      <header class="app-header">
        <a class="mobile-wordmark" href="#/${admin ? "admin" : "dashboard"}"
          >N<span> CLUB WORLD</span></a
        >
        <div class="header-breadcrumb">
          ${icon("leaf")} ${admin ? "Gestión del club" : "Tu lugar en el mundo"}
        </div>
        <div class="header-tools">
          <span id="sync-status" class="connection"
            ><span></span
            >${sessionState.mode === "demo" ? "DEMO LOCAL" : "Sincronizando"}</span
          ><a class="header-avatar" href="#/profile" aria-label="Mi perfil"
            >${e(
              p.full_name
                .split(" ")
                .map((s) => s[0])
                .slice(0, 2)
                .join(""),
            )}</a
          >
        </div>
      </header>
      ${sessionState.mode === "demo" ? `<div class="demo-bar"><span>DEMO</span><span class="demo-description">Datos de prueba · Sin acceso real</span><a href="#/demo">Cambiar perfil ${icon("arrow-up-right")}</a></div>` : ""}
      <main id="main" class="page-content">${content}</main>
      <footer class="app-footer">
        <span>N CLUB WORLD</span> Extraordinary by nature.
      </footer>
    </div>
    <nav
      class="bottom-nav ${admin ? "admin-bottom" : ""}"
      aria-label="Navegación móvil"
    >
      ${(admin
        ? [
            ["admin", "Inicio", "layout-dashboard"],
            ["admin/users", "Personas", "users"],
            ["reception", "Recepción", "bot"],
            ["admin/robots", "Robots", "activity"],
            ["profile", "Perfil", "user-round"],
          ]
        : [
            ["dashboard", "Inicio", "layout-dashboard"],
            ...(member
              ? [
                  ["bookings", "Reservar", "calendar-days"],
                  ["map", "Mapa", "map-pin"],
                ]
              : [["history", "Visitas", "history"]]),
            ["credential", "Mi QR", "qr-code"],
            ["profile", "Perfil", "user-round"],
          ]
      )
        .map(
          ([r, l, i]) =>
            `<a href="#/${r}" class="${route === r ? "active" : ""}" ${route === r ? 'aria-current="page"' : ""}>${icon(i)}<span>${l}</span></a>`,
        )
        .join("")}
    </nav>
  </div>`;
}
const sectionHead = (eyebrow, title, action = "") =>
  `<div class="section-heading"><div><span class="eyebrow">${eyebrow}</span><h2>${title}</h2></div>${action}</div>`;
export function reservationCard(r, data, { manage = false } = {}) {
  const service = data.services.find((s) => s.id === r.service_id);
  return /* HTML */ `<article class="reservation-card">
    <div class="reservation-date">
      <strong>${Number(r.reservation_date.slice(8))}</strong
      ><span
        >${new Intl.DateTimeFormat("es-CO", { month: "short" }).format(new Date(`${r.reservation_date}T12:00:00`)).replace(".", "")}</span
      >
    </div>
    <div class="reservation-details">
      <span class="eyebrow"
        >${service?.category === "golf" ? "GOLF EXPERIENCE" : "CLUB EXPERIENCE"}</span
      >
      <h3>${e(service?.name || "Servicio")}</h3>
      <p>
        ${icon("clock-3")} ${timeLabel(r.start_time)} – ${timeLabel(r.end_time)}
        <span>·</span> ${status(r.status)}
      </p>
      ${manage && r.status === "confirmed" ? `<div class="reservation-actions">${!r.legacy ? `<button class="text-button" data-action="edit-reservation" data-id="${e(r.id)}">${icon("pencil")} Modificar</button>` : '<span class="legacy-note">Reserva anterior · Puedes cancelarla y elegir un nuevo horario.</span>'}<button class="text-button danger-text" data-action="cancel-reservation" data-id="${e(r.id)}">Cancelar</button></div>` : ""}
    </div>
    ${!manage ? icon("chevron-right") : ""}
  </article>`;
}
export function dashboard(p, data) {
  const vip = p.role === "VIP";
  const member = isMember(p);
  const reservations = data.reservations
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
    );
  if (!member) return operationalDashboard(p, data);
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">TU ESPACIO EN N CLUB</span>
        <h1>
          ${vip ? "Bienvenida de nuevo" : "Bienvenido de nuevo"},<br
            class="mobile-only"
          />
          ${e(p.full_name.split(" ")[0])}<span class="gold-dot">.</span>
        </h1>
        <p>Reserva tu próximo plan o muestra tu QR al llegar.</p>
      </div>
      ${badge(p.role)}
    </div>
    <div class="member-grid">
      <section class="dashboard-hero">
        <img src="${images.golf}" alt="Campo de golf N Club World" />
        <div class="dashboard-hero-shade"></div>
        <div class="dashboard-hero-copy">
          <span class="eyebrow light">HAZ TIEMPO PARA TI</span>
          <h2>Tu tiempo.<br />Tu juego. <em>Tu mundo.</em></h2>
          <p>Hay momentos que merecen un escenario extraordinario.</p>
          <a href="#/bookings" class="button gold"
            >Reservar una experiencia ${icon("arrow-up-right")}</a
          >
        </div>
        <div class="hero-mini-note">
          ${icon("flag")} CINCO CANCHAS · UNA PASIÓN
        </div>
      </section>
      <section class="membership-panel">
        <div class="mini-heading">
          <h3>Tu membresía</h3>
          ${status(p.membership_status)}
        </div>
        ${membershipCard(p, true)}<a class="card-link" href="#/credential"
          >Ver mi credencial digital ${icon("qr-code")}</a
        >
      </section>
    </div>
    <div class="quick-actions">
      <a href="#/bookings"
        >${icon("flag")}<span>Reservar golf</span>${icon("arrow-up-right")}</a
      ><a href="#/bookings?category=restaurant"
        >${icon("utensils")}<span>Una buena mesa</span
        >${icon("arrow-up-right")}</a
      ><a href="#/bookings?tab=mine"
        >${icon("calendar-check")}<span>Mis reservas</span
        >${icon("arrow-up-right")}</a
      ><button data-action="assistance">
        ${icon(vip ? "crown" : "heart-handshake")}<span>${vip ? "Atención VIP" : "Solicitar asistencia"}</span>${icon("arrow-up-right")}
      </button>
    </div>
    ${clubMapBanner(p, data)}
    <div class="dashboard-lower">
      <section>
        ${sectionHead("CADA MOMENTO CUENTA", "Tu próxima experiencia", `<a class="text-link" href="#/bookings?tab=mine">Ver todas ${icon("arrow-right")}</a>`)}${
          reservations.length
            ? reservations
                .slice(0, 2)
                .map((r) => reservationCard(r, data))
                .join("")
            : empty(
                "Tu agenda, a tu ritmo",
                "Descubre el club y reserva tu próximo momento.",
                '<a href="#/bookings" class="text-link">Explorar disponibilidad →</a>',
              )
        }
      </section>
      <aside class="concierge-card">
        <span class="concierge-icon">${icon(vip ? "sparkles" : "leaf")}</span
        ><span class="eyebrow"
          >${vip ? "TU ASISTENTE VIP" : "INSPIRACIÓN N CLUB"}</span
        >
        <h3>${vip ? "Un día a tu altura." : "El placer de desconectar."}</h3>
        <p>
          ${vip ? "Después del green, una mesa especial. Descubre la propuesta de temporada de nuestro restaurante." : "Haz una pausa y descubre los sabores de temporada del Restaurante N Club."}
        </p>
        <a href="#/bookings?category=restaurant" class="text-link"
          >Descubrir mi recomendación ${icon("arrow-up-right")}</a
        >
      </aside>
    </div>
    ${sectionHead("SELECCIONADAS PARA TI", vip ? "El privilegio de lo extraordinario" : "Más razones para volver", `<a class="text-link" href="#/experiences">Descubrir ${icon("arrow-right")}</a>`)}
    <div class="experience-grid">
      ${experienceCards(p).slice(0, 3).join("")}
    </div>`;
}
function operationalDashboard(p, data) {
  const assignment = data.work_assignments.find(
    (w) => w.worker_id === p.id && w.status === "active",
  );
  const invite = data.invitations.find(
    (i) => i.guest_id === p.id && i.status === "active",
  );
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">TU ESPACIO EN EL CLUB</span>
        <h1>Hola, ${e(p.full_name.split(" ")[0])}.</h1>
        <p>Tu información de ingreso, en un solo lugar.</p>
      </div>
      ${badge(p.role)}
    </div>
    <div class="operational-grid">
      <section class="panel">
        <div class="mini-heading">
          <h2>Tu identificación</h2>
          ${status(p.membership_status)}
        </div>
        <div class="large-avatar role-${p.role.toLowerCase()}">
          ${icon(p.role === "EXTERNAL" ? "briefcase-business" : p.role === "STAFF" ? "user-round" : "ticket")}
        </div>
        <h2>${e(p.full_name)}</h2>
        <p>${e(p.position || roles[p.role])}</p>
        <div class="details-list">
          <div>
            <span>Identificador público</span><strong>${e(p.public_id)}</strong>
          </div>
          <div>
            <span
              >${p.role === "GUEST" ? "Destino autorizado" : "Zona de trabajo"}</span
            ><strong
              >${e(assignment?.authorized_zone || invite?.destination || "Pendiente de asignación")}</strong
            >
          </div>
          <div>
            <span>Vigencia</span
            ><strong
              >${assignment || invite ? `${clockLabel((assignment || invite).valid_from)} – ${clockLabel((assignment || invite).valid_until)}` : "Sin autorización vigente"}</strong
            >
          </div>
        </div>
        <a href="#/credential" class="button primary full"
          >Ver credencial ${icon("qr-code")}</a
        >
      </section>
      <section class="panel">
        <span class="eyebrow">ACCESO PERSONAL</span>
        <h2>Un ingreso sencillo y seguro.</h2>
        <p>
          Presenta tu credencial al robot de recepción. El equipo verificará tu
          identidad, horario y zona asignada.
        </p>
        <div class="notice">
          ${icon("shield-check")} La credencial identifica. El backend verifica
          los permisos y decide cada acceso.
        </div>
        <a href="#/history" class="text-link"
          >Consultar mis ingresos ${icon("arrow-right")}</a
        >
      </section>
    </div>`;
}

export function experienceCards(p) {
  return [
    {
      image: images.course,
      tag: "THE GOLF COLLECTION",
      title: "Donde el juego se vuelve arte.",
      text: "Cinco recorridos únicos. Un nuevo desafío cada día.",
      href: "#/bookings",
      label: "Descubrir el campo",
      ico: "flag",
    },
    {
      image: images.restaurant,
      tag: "TASTE THE EXTRAORDINARY",
      title: "Sabores que cuentan historias.",
      text: "Cocina de temporada en un entorno excepcional.",
      href: "#/bookings?category=restaurant",
      label: "Reservar una mesa",
      ico: "utensils",
    },
    {
      image: images.lounge,
      tag: "EXCLUSIVO BLACK VIP",
      title: "Un espacio solo para ti.",
      text: "Privacidad, comodidad y atención personalizada.",
      href: "#/bookings?category=lounge",
      label:
        p?.role === "VIP"
          ? "Explorar el lounge"
          : "Exclusivo para miembros VIP",
      ico: "crown",
      locked: p?.role !== "VIP",
    },
  ].map(
    (x) =>
      `<article class="experience-card"><div class="experience-image"><img src="${x.image}" alt="${e(x.title)}" loading="lazy"/><span>${icon(x.ico)} ${x.tag}</span></div><div class="experience-copy"><h3>${x.title}</h3><p>${x.text}</p>${x.locked ? `<span class="locked-link">${icon("lock-keyhole")} ${x.label}</span>` : `<a href="${p ? x.href : "#/login"}" class="text-link">${x.label} ${icon("arrow-up-right")}</a>`}</div></article>`,
  );
}
export function experiences(p) {
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">THE N CLUB COLLECTION</span>
        <h1>El arte de disfrutar.</h1>
        <p>
          Experiencias cuidadosamente elegidas para hacer de tu día algo
          extraordinario.
        </p>
      </div>
    </div>
    <div class="experience-grid">${experienceCards(p).join("")}</div>
    <section class="benefits-block">
      <span class="eyebrow">BLACK VIP MEMBERSHIP</span>
      <h2>El privilegio está en los detalles.</h2>
      <div class="benefits-grid">
        ${[
          [
            "crown",
            "Atención personalizada",
            "Un asistente dedicado a acompañar tu experiencia.",
          ],
          [
            "coffee",
            "Lounge privado",
            "Un lugar para disfrutar, conversar y desconectar.",
          ],
          [
            "sparkles",
            "Bienvenida exclusiva",
            "Recepción prioritaria y acompañamiento del robot VIP.",
          ],
        ]
          .map(([i, t, d]) => `<div>${icon(i)}<h3>${t}</h3><p>${d}</p></div>`)
          .join("")}
      </div>
      ${p?.role === "VIP" ? '<button class="button gold" data-action="assistance">Solicitar atención VIP</button>' : '<p class="benefit-note">Beneficios reservados a miembros con categoría VIP activa.</p>'}
    </section>`;
}

export function bookings(p, data, params) {
  const mine = params.get("tab") === "mine";
  const category = params.get("category") || "all";
  const reservations = data.reservations
    .filter((r) => r.user_id === p.id)
    .sort((a, b) =>
      (b.reservation_date + b.start_time).localeCompare(
        a.reservation_date + a.start_time,
      ),
    );
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">MAKE TIME FOR THE EXTRAORDINARY</span>
        <h1>Reserva tu próximo plan.</h1>
        <p>Elige una experiencia, la fecha y un horario disponible.</p>
      </div>
    </div>
    <div class="tabs">
      <a href="#/bookings" class="${!mine ? "active" : ""}">Reservar</a
      ><a href="#/bookings?tab=mine" class="${mine ? "active" : ""}"
        >Mis reservas
        <span
          >${reservations.filter((r) => r.status === "confirmed").length}</span
        ></a
      >
    </div>
    ${
      mine
        ? `<div class="my-reservations">${reservations.length ? reservations.map((r) => reservationCard(r, data, { manage: true })).join("") : empty("Tu próxima historia empieza aquí", "Todavía no tienes reservas.", '<a class="button primary" href="#/bookings">Explorar el club</a>')}</div>`
        : `<div class="filter-pills">${[
            ["all", "Todas"],
            ["golf", "Golf"],
            ["restaurant", "Gastronomía"],
            ["lounge", "Lounge VIP"],
          ]
            .map(
              ([v, l]) =>
                `<a class="${category === v ? "active" : ""}" href="#/bookings?category=${v}">${l}</a>`,
            )
            .join("")}</div><div class="services-grid">${data.services
            .filter(
              (s) =>
                s.active && (category === "all" || s.category === category),
            )
            .map(
              (s) =>
                `<article class="service-card"><div class="service-image"><img src="${e(s.image || images[s.category === "golf" ? "course" : s.category] || images.golf)}" alt="${e(s.name)}" loading="lazy"/>${s.vip_only ? `<span>${icon("crown")} BLACK VIP</span>` : ""}</div><div class="service-copy"><span class="eyebrow">${s.category === "golf" ? "GOLF EXPERIENCE" : s.category === "restaurant" ? "FINE DINING" : "PRIVATE LOUNGE"}</span><h3>${e(s.name)}</h3><p>${e(s.description)}</p><div class="service-bottom"><span>${icon("clock-3")} 60 minutos</span>${canBook(p, s) ? `<button class="button primary small" data-action="book" data-id="${e(s.id)}">Ver horarios ${icon("arrow-up-right")}</button>` : `<span class="locked-link">${icon("lock-keyhole")} ${s.vip_only ? "Exclusivo VIP" : "Membresía requerida"}</span>`}</div></div></article>`,
            )
            .join("")}</div>`
    }`;
}

export function credential(p) {
  return /* HTML */ `<div class="page-heading credential-heading">
      <div>
        <span class="eyebrow">YOUR KEY TO THE CLUB</span>
        <h1>Tu QR de ingreso.</h1>
        <p>
          Preséntalo en recepción. Se renueva automáticamente cada 15 minutos.
        </p>
      </div>
    </div>
    <div class="credential-layout single">
      <section
        class="credential-card qr-only ${p.role === "VIP" ? "vip" : "regular"}"
        aria-label="Credencial QR de ingreso"
      >
        <div class="qr-section">
          <div class="qr-card-top">
            <span class="eyebrow"
              >${
                sessionState.mode === "demo"
                  ? "CREDENCIAL DEMO · SIN ACCESO REAL"
                  : "CREDENCIAL DE VERIFICACIÓN"
              }</span
            >
            <span class="qr-live"><i aria-hidden="true"></i> EN VIVO</span>
          </div>
          <div class="qr-stage">
            <div id="qr-placeholder" class="qr-placeholder">
              ${icon("loader-circle")}
              <p>Preparando tu QR seguro…</p>
            </div>
            <canvas
              id="credential-qr"
              class="hidden"
              role="img"
              aria-label="Código QR de verificación temporal"
            ></canvas>
          </div>
          <p class="qr-expiry">
            <span id="qr-expiry-copy">Generando tu credencial…</span>
          </p>
          <div class="qr-progress" aria-hidden="true">
            <span id="qr-progress"></span>
          </div>
          <button
            class="text-button qr-download hidden"
            id="download-qr"
            data-action="download-qr"
          >
            ${icon("download")} Guardar imagen
          </button>
          <button
            class="button primary full qr-retry hidden"
            id="retry-qr"
            data-action="generate-qr"
          >
            ${icon("refresh-cw")} Reintentar
          </button>
          <p class="qr-note">
            ${icon("shield-check")}
            <span
              >Tu código es temporal y personal. Cada renovación invalida el
              anterior y el acceso se verifica en recepción.</span
            >
          </p>
        </div>
      </section>
    </div>`;
}

export function eventTable(events, data) {
  return events.length
    ? `<div class="table-scroll"><table><thead><tr><th>Visitante</th><th>Hora</th><th>Resultado</th><th>Destino</th><th>Robot</th><th>Origen</th></tr></thead><tbody>${events.map((ev) => `<tr><td><strong>${e(data.profiles.find((p) => p.id === ev.visitor_id)?.full_name || "Visitante")}</strong><small>${e(roles[ev.role])}</small></td><td>${clockLabel(ev.created_at)}<small>${dateLabel(ev.created_at)}</small></td><td>${status(ev.access_status)}</td><td>${e(ev.destination || "Recepción")}</td><td>${ev.robot_target === "robot2" ? "AGIBOT 02" : "AGIBOT 01"}${ev.event_type === "vip_handoff" ? "<small>Transferencia VIP</small>" : ""}</td><td><span class="${ev.simulation ? "demo-tag" : "live-tag"}">${ev.simulation ? "DEMO" : "BACKEND"}</span></td></tr>`).join("")}</tbody></table></div>`
    : empty(
        "El próximo capítulo está por comenzar",
        "Los eventos aparecerán cuando se registre una recepción.",
      );
}
export function history(p, data) {
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">MOMENTOS EN TU CLUB</span>
        <h1>Tu historial de visitas.</h1>
        <p>Recepciones, destinos y experiencias que forman parte de ti.</p>
      </div>
    </div>
    <section class="panel">
      ${eventTable(
        data.access_events.filter((ev) => ev.visitor_id === p.id),
        data,
      )}
    </section>`;
}
export function profile(p) {
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">MI CUENTA</span>
        <h1>Tu perfil.</h1>
        <p>Una experiencia que empieza por conocerte.</p>
      </div>
    </div>
    <section class="panel profile-panel">
      <div class="large-avatar">${e(p.full_name[0])}</div>
      <h2>${e(p.full_name)}</h2>
      ${badge(p.role)}
      <div class="details-list">
        <div>
          <span>Correo electrónico</span
          ><strong>${e(p.email || "Sin cuenta asociada")}</strong>
        </div>
        <div><span>Estado</span>${status(p.membership_status)}</div>
        <div><span>Identificador</span><strong>${e(p.public_id)}</strong></div>
      </div>
      <div class="notice">
        ${icon("shield")}
        <p>
          Tu categoría la gestiona el club. Para cambios de membresía o para
          registrar consentimiento facial, solicita atención personalizada a
          recepción.
        </p>
      </div>
      <button class="button outline full" data-action="logout">
        ${icon("log-out")} Cerrar sesión</button
      >${sessionState.mode === "demo" ? '<a href="#/demo" class="text-link">Cambiar perfil de demostración →</a>' : ""}
      ${isMember(p) ? `<a href="#/map" class="profile-history">${icon("map-pin")} Mapa del club ${icon("chevron-right")}</a><a href="#/history" class="profile-history">${icon("history")} Ver mis visitas ${icon("chevron-right")}</a>` : ""}
    </section>`;
}

export function adminPage(tab, data) {
  const names = {
    users: "Personas del club",
    reservations: "Reservas",
    invitations: "Invitaciones",
    work: "Turnos y órdenes de trabajo",
    access: "Registro de accesos",
    robots: "Seguimiento de robots",
  };
  if (!tab) {
    const stats = [
      ["Miembros", data.profiles.filter(isMember).length, "users"],
      [
        "VIP activos",
        data.profiles.filter(
          (p) => p.role === "VIP" && p.membership_status === "active",
        ).length,
        "crown",
      ],
      [
        "Miembros regulares",
        data.profiles.filter((p) => p.role === "REGULAR").length,
        "flag",
      ],
      [
        "Invitados esperados",
        data.invitations.filter(
          (i) => i.visit_date === today() && i.status === "active",
        ).length,
        "ticket",
      ],
      [
        "Personal autorizado",
        data.work_assignments.filter(
          (w) =>
            w.assignment_type === "SHIFT" &&
            w.status === "active" &&
            new Date(w.valid_from) <= new Date() &&
            new Date(w.valid_until) > new Date(),
        ).length,
        "user-round",
      ],
      [
        "Externos programados",
        data.work_assignments.filter(
          (w) =>
            w.assignment_type === "EXTERNAL_ORDER" &&
            w.status === "active" &&
            new Date(w.valid_until) > new Date(),
        ).length,
        "briefcase-business",
      ],
      [
        "Reservas de hoy",
        data.reservations.filter(
          (r) => r.reservation_date === today() && r.status === "confirmed",
        ).length,
        "calendar-check",
      ],
    ];
    return /* HTML */ `<div class="page-heading">
        <div>
          <span class="eyebrow">CLUB MANAGEMENT</span>
          <h1>Una visión de tu club.</h1>
          <p>${dateLabel(today())} · Hospitalidad que se anticipa.</p>
        </div>
        <a class="button primary" href="#/reception"
          >${icon("bot")} Recepción ${icon("arrow-up-right")}</a
        >
      </div>
      <div class="stats-grid">
        ${stats.map(([l, v, i]) => `<div class="stat-card">${icon(i)}<strong>${v.toString().padStart(2, "0")}</strong><span>${l}</span></div>`).join("")}
      </div>
      <section class="admin-reception-banner">
        <div>
          <span class="eyebrow light">THE FUTURE OF HOSPITALITY</span>
          <h2>Una bienvenida extraordinaria.</h2>
          <p>Dos robots AGIBOT. Cinco experiencias personalizadas.</p>
        </div>
        <a href="#/reception" class="button gold"
          >Abrir centro de recepción ${icon("arrow-up-right")}</a
        >
      </section>
      <section class="panel">
        ${sectionHead("EN TIEMPO REAL", "Últimas recepciones", `<a href="#/admin/access" class="text-link">Ver todas ${icon("arrow-right")}</a>`)}${eventTable(data.access_events.slice(0, 6), data)}
      </section>
      <div class="admin-links">
        ${[
          ["users", "Personas del club", "users"],
          ["reservations", "Reservas", "calendar-days"],
          ["invitations", "Crear invitación", "ticket"],
          ["work", "Órdenes y turnos", "briefcase-business"],
          ["access", "Registro de accesos", "activity"],
          ["robots", "Seguimiento de robots", "bot"],
        ]
          .map(
            ([r, l, i]) =>
              `<a href="#/admin/${r}" class="panel">${icon(i)}<h3>${l}</h3>${icon("arrow-up-right")}</a>`,
          )
          .join("")}
      </div>`;
  }
  let content = "";
  if (tab === "users")
    content = `<div class="search-bar">${icon("search")}<input id="user-search" type="search" placeholder="Buscar por nombre o categoría" aria-label="Buscar usuarios"/></div><div class="table-scroll"><table id="users-table"><thead><tr><th>Persona</th><th>Categoría</th><th>Estado</th><th>Registro</th><th>Acciones</th></tr></thead><tbody>${data.profiles.map((p) => `<tr data-search="${e(`${p.full_name} ${roles[p.role]}`.toLowerCase())}"><td><strong>${e(p.full_name)}</strong><small>${e(p.email || p.public_id)}</small></td><td>${badge(p.role)}</td><td>${status(p.membership_status)}</td><td>${dateLabel(p.created_at)}</td><td><button class="icon-button" data-action="edit-user" data-id="${e(p.id)}" aria-label="Editar ${e(p.full_name)}">${icon("pencil")}</button><button class="icon-button" data-action="visitor-qr" data-id="${e(p.id)}" aria-label="Generar QR de ${e(p.full_name)}">${icon("qr-code")}</button></td></tr>`).join("")}</tbody></table></div>`;
  if (tab === "reservations")
    content = `<div class="table-scroll"><table><thead><tr><th>Miembro</th><th>Servicio</th><th>Fecha</th><th>Horario</th><th>Estado</th><th>Acción</th></tr></thead><tbody>${data.reservations.map((r) => `<tr><td>${e(data.profiles.find((p) => p.id === r.user_id)?.full_name)}</td><td>${e(data.services.find((s) => s.id === r.service_id)?.name)}</td><td>${dateLabel(r.reservation_date)}</td><td>${timeLabel(r.start_time)} – ${timeLabel(r.end_time)}</td><td>${status(r.status)}</td><td>${r.status === "confirmed" ? `<button class="text-button danger-text" data-action="cancel-reservation" data-id="${e(r.id)}">Cancelar</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>`;
  if (tab === "invitations" || tab === "work") {
    const table = tab === "invitations" ? "invitations" : "work_assignments";
    const rows = data[table];
    content = `<div class="table-scroll"><table><thead><tr><th>${tab === "invitations" ? "Invitado" : "Persona / Empresa"}</th><th>${tab === "invitations" ? "Anfitrión" : "Tipo"}</th><th>Vigencia</th><th>Destino</th><th>Estado</th><th>Acción</th></tr></thead><tbody>${rows.map((row) => `<tr><td><strong>${e(data.profiles.find((p) => p.id === (row.guest_id || row.worker_id))?.full_name)}</strong><small>${e(row.company || "Invitación personal")}</small></td><td>${tab === "invitations" ? e(data.profiles.find((p) => p.id === row.host_id)?.full_name) : row.assignment_type === "SHIFT" ? "Turno de personal" : "Orden externa"}</td><td>${dateLabel(row.valid_from)}<small>${clockLabel(row.valid_from)} – ${clockLabel(row.valid_until)}</small></td><td>${e(row.destination || row.authorized_zone)}</td><td>${status(row.status)}</td><td>${row.status === "active" ? `<button class="text-button danger-text" data-action="revoke" data-table="${table}" data-id="${e(row.id)}">Revocar</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>${!rows.length ? empty("Sin registros", "Crea una autorización temporal para comenzar.") : ""}`;
  }
  if (tab === "access") content = eventTable(data.access_events, data);
  return /* HTML */ `<div class="page-heading">
      <div>
        <span class="eyebrow">CLUB MANAGEMENT</span>
        <h1>${names[tab] || "Administración"}.</h1>
        <p>
          ${["users", "invitations", "work"].includes(tab) ? "Invitados, personal y proveedores se gestionan aquí. No necesitan una cuenta en la app." : "Consulta y gestiona la actividad del club."}
        </p>
      </div>
      ${tab === "invitations" || tab === "work" ? `<button class="button primary" data-action="new-visitor" data-type="${tab === "invitations" ? "GUEST" : "EXTERNAL"}">${icon("plus")} ${tab === "invitations" ? "Nueva invitación" : "Nuevo turno u orden"}</button>` : ""}
    </div>
    <div class="admin-mobile-tabs">
      ${[
        ["", "General"],
        ["users", "Personas"],
        ["reservations", "Reservas"],
        ["invitations", "Invitados"],
        ["work", "Órdenes"],
        ["access", "Accesos"],
        ["robots", "Robots"],
      ]
        .map(
          ([r, l]) =>
            `<a class="${tab === r ? "active" : ""}" href="#/admin${r ? "/" + r : ""}">${l}</a>`,
        )
        .join("")}
    </div>
      <section class="panel admin-panel">${tab === "robots" ? adminRobotMonitor(data.robot_monitor) : content}</section>`;
}

export function adminRobotMonitor(monitor) {
  const connected = monitor?.connected === true;
  const cameraUrl =
    connected && typeof monitor.camera_stream_url === "string"
      ? monitor.camera_stream_url
      : "";
  const latest = Array.isArray(monitor?.events) ? monitor.events.slice(0, 8) : [];
  const transcripts = Array.isArray(monitor?.transcripts)
    ? monitor.transcripts.slice(0, 6)
    : [];
  const active = Array.isArray(monitor?.active_sessions)
    ? monitor.active_sessions
    : [];
  const current = latest[0];
  const mic = monitor?.microphone || {};
  const roleNames = { VIP: "VIP", REGULAR: "Miembro", GUEST: "Invitado", STAFF: "Personal", EXTERNAL: "Proveedor" };
  const categoryNames = { VIP: "VIP", REGULAR: "Miembro", INVITADO: "Invitado", PERSONAL_INTERNO: "Personal", TRABAJADOR_EXTERNO: "Proveedor" };
  const decisionNames = { AUTORIZADO: "Autorizado", DENEGADO: "Denegado", REVISION: "Revisión manual", ACOMPANAMIENTO: "Acompañamiento", PENDIENTE: "Pendiente" };
  const accessNames = { authorized: "Autorizado", review: "Revisión", denied: "Denegado", pending: "Pendiente" };
  const decisionClass = (d) =>
    ({ AUTORIZADO: "authorized", DENEGADO: "denied", REVISION: "review", ACOMPANAMIENTO: "pending" })[d] || "pending";
  const time = (v) =>
    v
      ? new Date(v).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
      : "—";
  return `<div class="robot-monitor" data-robot-monitor data-robot-id="${e(monitor?.robot_id || "")}">
    <div class="robot-monitor-top"><div><span class="eyebrow">CENTRO DE OPERACIONES</span><h2>Recepción AGIBOT</h2><p>Vista del robot, voz transcrita, identificación y decisión de cada llegada.</p></div><div class="robot-badges">${monitor?.simulation ? `<span class="demo-tag">SIMULACIÓN</span>` : ""}<span class="robot-connection ${connected ? "is-online" : "is-offline"}"><i></i>${connected ? "CONECTADO" : "SIN CONEXIÓN"}</span></div></div>
    ${monitor?.error ? `<div class="notice robot-monitor-notice"><p>${e(monitor.error)}</p></div>` : ""}
    ${monitor?.persistence && !monitor.persistence.ok ? `<div class="notice robot-monitor-notice">${icon("alert-circle")}<p>Persistencia degradada: ${e(Object.keys(monitor.persistence.degraded).join(", "))}. Ejecute supabase/recepcion_robot.sql; mientras tanto el historial vive solo en memoria.</p></div>` : ""}
    <div class="robot-status-strip">
      <span class="${connected ? "ok" : "off"}">${icon(connected ? "wifi" : "wifi-off")}Robot<strong>${connected ? "En línea" : "Desconectado"}</strong></span>
      <span class="${monitor?.camera?.live ? "ok" : "off"}">${icon("camera")}Cámara<strong>${monitor?.camera?.live ? "Transmitiendo" : monitor?.camera?.ok ? "Sin fotogramas" : "Sin señal"}</strong></span>
      <span class="${mic.ok ? "ok" : "off"}">${icon("mic")}Micrófono<strong>${e(mic.ok ? mic.state || "activo" : "Sin señal")}</strong></span>
      <span>${icon("radio")}Sesiones activas<strong>${active.length}</strong></span>
    </div>
    <div class="robot-monitor-grid"><section class="robot-camera panel"><div class="monitor-section-heading"><div><span class="eyebrow">CÁMARA EN VIVO</span><strong>${e(monitor?.robot_name || "AGIBOT recepción")}</strong></div><span>${cameraUrl ? "STREAM PRIVADO" : "ESPERANDO SEÑAL"}</span></div>${cameraUrl ? `<img data-robot-stream src="${e(cameraUrl)}" alt="Transmisión de cámara del robot" />` : `<div class="camera-placeholder">${icon("camera")}<strong>${connected ? "Cámara sin señal" : "La transmisión aparecerá cuando el agente del robot se conecte"}</strong><span>Stream MJPEG privado con token de corta duración; no se graba video.</span></div>`}</section>
      <section class="robot-listening panel"><div class="monitor-section-heading"><div><span class="eyebrow">ESCUCHA Y VOZ · EN VIVO</span><strong>Transcripción</strong></div>${icon("audio-lines")}</div>${monitor?.last_heard ? `<p class="heard-text" data-live-transcript>“${e(monitor.last_heard.transcript || "Audio recibido; sin transcripción")}”</p><div class="heard-meta">${e(monitor.last_heard.language || "Idioma no indicado")} · ${e(monitor.last_heard.intent || "")} · ${e(time(monitor.last_heard.created_at))}</div>${monitor.last_heard.audio_url ? `<audio controls preload="none" src="${e(monitor.last_heard.audio_url)}">El navegador no admite reproducción de audio.</audio>` : ""}` : `<div class="listening-empty">${icon("mic")}<span data-live-transcript>${connected ? "Esperando una interacción de voz…" : "La transcripción aparecerá al conectar el robot."}</span></div>`}
        ${transcripts.length > 1 ? `<ul class="transcript-list">${transcripts.slice(1).map((t) => `<li><span>${e(time(t.created_at))}</span>${e(t.texto)}</li>`).join("")}</ul>` : ""}
        <p class="monitor-privacy">La voz solo orienta el diálogo: nunca confirma identidad. Los clips se guardan únicamente con consentimiento y política del club.</p></section></div>
    ${
      current
        ? `<section class="panel monitor-current"><div class="monitor-section-heading"><div><span class="eyebrow">ÚLTIMA ATENCIÓN · ${e(time(current.created_at))}</span><strong>${e(current.display_name || "Visitante")}</strong></div><span class="status status-${decisionClass(current.decision)}"><span></span>${e(decisionNames[current.decision] || current.decision || "Sin decisión")}</span></div>
      <div class="details-list monitor-details">
        <div><span>Categoría detectada</span><strong>${e(categoryNames[current.category_detected] || "—")}</strong></div>
        <div><span>Categoría confirmada</span><strong>${e(roleNames[current.role] || "No confirmada")}</strong></div>
        <div><span>Método</span><strong>${e(current.method)}</strong></div>
        <div><span>Destino</span><strong>${e(current.destination || "—")}</strong></div>
        <div><span>Justificación</span><strong>${e(current.reason || "—")}</strong></div>
      </div>
      ${Array.isArray(current.checks) && current.checks.length ? `<ul class="check-list">${current.checks.map((c) => `<li class="${c.ok ? "ok" : "fail"}">${icon(c.ok ? "check-circle-2" : "alert-circle")}<strong>${e(c.name)}</strong><span>${e(c.detail)}</span></li>`).join("")}</ul>` : ""}
      ${current.route?.steps ? routeCard(current.route, { title: "Ruta entregada al visitante", compact: true }) : ""}
      </section>`
        : ""
    }
    <section class="classification-panel panel"><div class="monitor-section-heading"><div><span class="eyebrow">HISTORIAL Y EVIDENCIAS</span><strong>Interacciones</strong></div><span>Tiempo real · respaldo cada 3 s</span></div>${latest.length ? `<div class="table-scroll"><table><thead><tr><th>Hora</th><th>Persona</th><th>Detectada</th><th>Confirmada</th><th>Método</th><th>Decisión</th><th>Voz</th><th>Robot</th></tr></thead><tbody>${latest.map((item) => `<tr><td>${e(time(item.created_at))}</td><td>${e(item.display_name || "Visitante")}${item.simulation ? "<small>simulación</small>" : ""}</td><td>${e(categoryNames[item.category_detected] || "—")}</td><td>${e(roleNames[item.role] || "—")}</td><td>${e(item.method || "—")}</td><td>${e(decisionNames[item.decision] || accessNames[item.access] || "Sin decisión")}</td><td>${e((item.transcripts || []).join(" · ") || "—")}</td><td>${e(item.robot_name || item.robot_target || "AGIBOT")}</td></tr>`).join("")}</tbody></table></div>` : Array.isArray(monitor?.stored_sessions) && monitor.stored_sessions.length ? `<div class="table-scroll"><table><thead><tr><th>Inicio</th><th>Robot</th><th>Detectada</th><th>Confirmada</th><th>Método</th><th>Decisión</th></tr></thead><tbody>${monitor.stored_sessions.map((s) => `<tr><td>${e(time(s.iniciada_en))}</td><td>${e(s.robot_id)}</td><td>${e(categoryNames[s.categoria_detectada] || "—")}</td><td>${e(categoryNames[s.categoria_confirmada] || "—")}</td><td>${e((s.metodo_verificacion || []).join(" + ") || "—")}</td><td>${e(decisionNames[s.decision] || s.estado)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="monitor-no-events">${icon("scan-eye")}<span>${connected ? "Todavía no hay interacciones reportadas." : "Los eventos se cargarán cuando /robot/monitor esté disponible."}</span></div>`}</section>
    <p class="monitor-updated">${monitor?.updated_at ? `Última actualización: ${e(new Date(monitor.updated_at).toLocaleTimeString("es-CO"))}` : "El monitor requiere una sesión ADMIN real y el backend de robots."}</p>
  </div>`;
}

export function reception(data, flow) {
  const f = flow || {};
  const p = data.profiles.find((p) => p.id === f.visitor_id);
  return /* HTML */ `<div class="page-heading reception-heading">
      <div>
        <span class="eyebrow">INTELLIGENT HOSPITALITY</span>
        <h1>
          N CLUB <span class="heading-divider">/</span>
          <span class="sans-heading">SMART RECEPTION</span>
        </h1>
        <p>Una experiencia diferente para cada persona.</p>
      </div>
      <span class="demo-tag"
        >${f.simulation !== false ? "MODO DEMO" : "EVALUACIÓN BACKEND"}</span
      >
    </div>
    <div class="reception-grid">
      <section
        class="robot-card ${f.robot_target === "robot1" ? "robot-active" : ""}"
      >
        <div class="robot-head">
          <span class="eyebrow">AGIBOT 01</span
          ><span class="robot-status"
            >${f.busy ? "Procesando" : "Recepción principal"}</span
          >
        </div>
        <div class="robot-visual">
          ${robotIllustration(false)}<span class="robot-orbit"></span>
        </div>
        <div class="robot-title">
          <h2>Tu primera bienvenida.</h2>
          <p>Identificación y verificación de visitantes</p>
        </div>
        <div class="robot-footer">
          <span class="pulse-dot"></span
          >${f.busy ? "Visitante en recepción" : f.stage || "Esperando visitante"}<span
            >ROBOT 01</span
          >
        </div>
      </section>
      <section class="reception-visitor panel">
        <div class="mini-heading">
          <span class="eyebrow">VISITANTE ACTUAL</span
          >${f.access ? status(f.access) : '<span class="status status-pending"><span></span>En espera</span>'}
        </div>
        <div class="visitor-avatar ${f.role === "VIP" ? "vip-avatar" : ""}">
          ${icon(f.role === "VIP" ? "crown" : "user-round")}
        </div>
        <h2>
          ${e(p?.full_name || f.visitor_name || (f.visitor_id ? "Visitante identificado" : "Tu próxima bienvenida"))}
        </h2>
        <p>
          ${f.role ? badge(f.role) : "Cada visitante, una experiencia única."}
        </p>
        <div class="details-list">
          <div>
            <span>Identidad</span
            ><strong
              >${f.identity_confirmed ? "Confirmada" : f.busy ? "Verificando…" : "Pendiente"}</strong
            >
          </div>
          <div>
            <span>Método</span
            ><strong>${f.method || "QR / identificación voluntaria"}</strong>
          </div>
          <div>
            <span>Destino</span
            ><strong>${e(f.route?.destination_label || f.destination || "Pendiente de validación")}</strong>
          </div>
          <div>
            <span>Reserva asociada</span
            ><strong
              >${e(f.reservation_label || "Sin confirmación del backend")}</strong
            >
          </div>
          <div>
            <span>Último evento</span
            ><strong class="event-code"
              >${e(f.event_type || "waiting_for_visitor")}</strong
            >
          </div>
        </div>
        <div class="reception-message" aria-live="polite">
          ${icon("message-circle")}
          <p>
            ${e(f.message || "Bienvenido a N Club World. Será un placer acompañarte.")}
          </p>
        </div>
        ${f.reason ? `<p class="flow-reason">${e(f.reason)}</p>` : ""}
      </section>
      <section
        class="robot-card vip-robot ${f.robot_target === "robot2" ? "robot-active" : ""}"
      >
        <div class="robot-head">
          <span class="eyebrow">AGIBOT 02</span
          ><span class="vip-small">${icon("crown")} VIP CONCIERGE</span>
        </div>
        <div class="robot-visual">
          ${robotIllustration(true)}<span class="robot-orbit"></span>
        </div>
        <div class="robot-title">
          <h2>El privilegio de la atención.</h2>
          <p>Hospitalidad dedicada a miembros VIP</p>
        </div>
        <div class="robot-footer">
          <span
            class="pulse-dot ${f.robot_target !== "robot2" ? "inactive" : ""}"
          ></span
          >${f.robot_target === "robot2" ? "Atención VIP activa" : "En espera de transferencia"}<span
            >ROBOT 02</span
          >
        </div>
      </section>
    </div>
    ${f.route && !f.busy ? routeCard(f.route, { qrId: "route-qr", title: f.simulation !== false ? "Recorrido · simulación" : "Recorrido autorizado" }) : ""}
    <section class="panel simulation-panel">
      <div class="section-heading">
        <div>
          <span class="eyebrow">FIVE GUESTS. FIVE EXPERIENCES.</span>
          <h2>Elige una bienvenida.</h2>
          <p>
            Simulación exclusiva de administración. Nunca autoriza accesos
            físicos.
          </p>
        </div>
        <span id="backend-status" class="connection"
          ><span></span
          >${backendUrl ? "Backend por comprobar" : "Backend sin configurar"}</span
        >
      </div>
      <div class="simulation-controls">
        <label
          >Resultado de prueba<select
            id="simulation-outcome"
            ${f.busy ? "disabled" : ""}
          >
            <option
              value="authorized"
              ${f.requested_outcome === "authorized" ? "selected" : ""}
            >
              Evaluar escenario
            </option>
            <option
              value="review"
              ${f.requested_outcome === "review" ? "selected" : ""}
            >
              Revisión requerida
            </option>
            <option
              value="denied"
              ${f.requested_outcome === "denied" ? "selected" : ""}
            >
              Acceso denegado
            </option>
          </select></label
        ><button class="text-button" data-action="health">
          ${icon("refresh-cw")} Comprobar backend
        </button>
      </div>
      <div class="scenario-buttons">
        ${[
          ["VIP", "crown", "VIP", "Atención extraordinaria"],
          ["REGULAR", "flag", "Miembro", "El placer de volver"],
          ["GUEST", "ticket", "Invitado", "Una invitación especial"],
          ["STAFF", "user-round", "Personal", "Parte de nuestra esencia"],
          [
            "EXTERNAL",
            "briefcase-business",
            "Externo",
            "Acceso a su zona de trabajo",
          ],
        ]
          .map(
            ([r, i, l, s]) =>
              `<button data-action="simulate" data-role="${r}" class="scenario-button ${r === "VIP" ? "vip-scenario" : ""}" ${f.busy ? "disabled" : ""}>${icon(i)}<strong>Simular ${l}</strong><small>${s}</small>${icon("arrow-up-right")}</button>`,
          )
          .join("")}
      </div>
      <div class="flow-steps">
        ${["Detección", "Identificación", "Verificación", "Permisos", "Recepción"].map((s, i) => `<div class="${(f.step ?? -1) >= i ? "done" : ""}"><span>${(f.step ?? -1) >= i ? icon("check") : i + 1}</span>${s}</div>`).join("")}
      </div>
      <p class="simulation-note">
        ${icon("shield-check")}
        ${sessionState.mode === "demo" ? "DEMO local aislada: resultados ficticios. No se enviarán órdenes a los robots." : backendUrl ? "Se solicitará evaluación DEMO a FastAPI. Si falla, se mostrará un resultado ficticio marcado como simulado." : "Sin backend: resultados ficticios DEMO. No se enviarán órdenes a los robots."}
      </p>
    </section>
    <section class="panel real-validation">
      <span class="eyebrow">VERIFICACIÓN REAL · SOLO CON BACKEND</span>
      <h2>Verificar una credencial.</h2>
      <p>
        Pega el token escaneado por recepción. FastAPI verificará la credencial
        y decidirá el acceso.
      </p>
      <form id="access-form">
        <label class="sr-only" for="access-token"
          >Token opaco de credencial</label
        ><input
          id="access-token"
          name="token"
          type="password"
          placeholder="nclub:v1:…"
          required
          maxlength="500"
          autocomplete="off"
          ${sessionState.mode === "demo" || !backendUrl ? "disabled" : ""}
        /><button
          class="button primary"
          ${sessionState.mode === "demo" || !backendUrl || f.busy ? "disabled" : ""}
        >
          ${icon("scan-line")} Verificar con backend
        </button>
      </form>
    </section>
    <section class="panel">
      ${sectionHead("RECEPTION JOURNAL", "Últimos eventos")}${eventTable(data.access_events.slice(0, 8), data)}
    </section>`;
}
function robotIllustration(vip) {
  return /* HTML */ `<svg
    class="robot-svg"
    viewBox="0 0 230 240"
    fill="none"
    role="img"
    aria-label="Ilustración conceptual del robot AGIBOT ${vip ? "VIP" : "de recepción"}"
  >
    <defs>
      <linearGradient
        id="body-${vip}"
        x1="50"
        y1="30"
        x2="180"
        y2="240"
        gradientUnits="userSpaceOnUse"
      >
        <stop stop-color="#fff" />
        <stop offset=".5" stop-color="#dce2df" />
        <stop offset="1" stop-color="#a6b5b0" />
      </linearGradient>
      <linearGradient id="visor-${vip}">
        <stop stop-color="#1d3532" />
        <stop offset="1" stop-color="#081c18" />
      </linearGradient>
    </defs>
    <ellipse cx="115" cy="232" rx="73" ry="6" fill="#19392c" opacity=".12" />
    <path d="M91 90h48v31H91z" fill="#8da29a" />
    <rect
      x="71"
      y="20"
      width="88"
      height="80"
      rx="30"
      fill="url(#body-${vip})"
      stroke="#e8eee9"
    />
    <rect
      x="77"
      y="37"
      width="76"
      height="40"
      rx="19"
      fill="url(#visor-${vip})"
    />
    <path
      d="M95 57h9m22 0h9"
      stroke="${vip ? "#c8a96b" : "#79d7bf"}"
      stroke-width="4"
      stroke-linecap="round"
    />
    <path
      d="M107 84h16"
      stroke="#a6b4ad"
      stroke-width="2"
      stroke-linecap="round"
    />
    <path
      d="M78 112c-14 0-20 11-20 28l-6 62c-2 16 15 20 20 5l9-55m71-40c14 0 20 11 20 28l6 62c2 16-15 20-20 5l-9-55"
      fill="url(#body-${vip})"
      stroke="#c8d3cc"
    />
    <path
      d="M91 109h48c16 0 25 13 24 31l-6 66c-1 15-12 24-26 24H99c-14 0-25-9-26-24l-6-66c-1-18 8-31 24-31z"
      fill="url(#body-${vip})"
      stroke="#cbd5ce"
    />
    <path
      d="M81 121c23 13 45 13 68 0l-3 45c-20 10-40 10-62 0z"
      fill="${vip ? "#173e31" : "#f7faf7"}"
    />
    <circle
      cx="115"
      cy="149"
      r="8"
      stroke="${vip ? "#c8a96b" : "#78978a"}"
      stroke-width="1.5"
    />
    <path d="M112 154v-10l6 10v-10" stroke="${vip ? "#c8a96b" : "#78978a"}" />
    <path
      d="M99 219v10m32-10v10"
      stroke="#8fa39a"
      stroke-width="10"
      stroke-linecap="round"
    />
  </svg>`;
}

export function publicPage(content) {
  return /* HTML */ `<div class="public-page">
    <header class="public-header">
      ${brand()}<a class="button outline small" href="#/login"
        >Mi membresía ${icon("arrow-up-right")}</a
      >
    </header>
    <main id="main" class="public-content">${content}</main>
    <footer class="landing-bottom">
      <p>N Club World — The Future of Exclusive Hospitality</p>
      <a href="#/">Volver al inicio</a>
    </footer>
  </div>`;
}
export function memberships() {
  return publicPage(
    `<div class="page-heading"><div><span class="eyebrow">A PLACE TO BELONG</span><h1>Elige vivir lo extraordinario.</h1><p>Dos formas de pertenecer. La misma pasión por lo excepcional.</p></div></div><div class="membership-options">${["REGULAR", "VIP"].map((role) => `<section class="panel ${role === "VIP" ? "premium-option" : ""}">${icon(role === "VIP" ? "crown" : "flag")}<span class="eyebrow">${role === "VIP" ? "BLACK VIP" : "SIGNATURE"} MEMBERSHIP</span><h2>${role === "VIP" ? "Una experiencia sin igual." : "Tu lugar en el club."}</h2><p>${role === "VIP" ? "Atención personalizada, lounge privado y recepción prioritaria, además de todos los servicios de tu club." : "Golf, gastronomía y momentos que merecen formar parte de tu día."}</p><ul><li>Reservas de golf y restaurante</li><li>Credencial digital segura</li><li>Historial y asistencia del club</li>${role === "VIP" ? "<li>Asistente y recepción VIP</li><li>Acceso al Lounge VIP</li>" : ""}</ul><a href="#/login" class="button ${role === "VIP" ? "gold" : "primary"}">Acceder a mi membresía ${icon("arrow-up-right")}</a></section>`).join("")}</div>`,
  );
}
