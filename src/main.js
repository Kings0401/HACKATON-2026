import "./styles.css";
import "./responsive.css";
import "./theme.css";
import * as pages from "./pages.js";
import {
  sessionState,
  restoreSession,
  login,
  loginDemo,
  logout,
  loadData,
  book,
  cancel,
  availability,
  issueCredential,
  updateProfile,
  createVisitor,
  revoke,
  updateAuthorizationDates,
  appendDemoEvent,
} from "./data.js";
import { supabase, demoEnabled, backendUrl } from "./config.js";
import { subscribe } from "./realtime.js";
import {
  clubMapPage,
  selectMapDestination,
  revealMapRoute,
} from "./clubmap.js";
import { api, validateDecision, memoryToken } from "./api.js";
import {
  deviceLabActive,
  startDeviceLab,
  stopDeviceLab,
  sendLabText,
  toggleLabMic,
  setLabVoice,
  markAgibot,
  photoToJpeg,
} from "./devicelab.js";
import {
  routePage,
  computeRoute,
  roleToCategory,
  shareUrlFor,
  revealRoutes,
} from "./navigation.js";
import { evaluateDemo, readDemo, writeDemo, seed } from "./demo.js";
import {
  icon,
  hydrate,
  toast,
  modal,
  closeModal,
  drawQR,
  drawLinkQR,
  empty,
} from "./ui.js";
import {
  escape as e,
  roles,
  today,
  dateAfter,
  dateLabel,
  slots,
  canBook,
  readableError,
  images,
  isMember,
  canUseApp,
  uid,
} from "./lib.js";

let data = null,
  flow = null,
  unsubscribe = null,
  subscribedId = null,
  renderId = 0,
  refreshBusy = false,
  formBusy = false,
  robotMonitorTimer = null,
  robotMonitorBusy = false,
  monitorChannel = null,
  monitorRefreshQueued = null;
let syncStatus = "connecting";
const QR_ROTATION_MS = 15 * 60 * 1000;
let qrTimer = null,
  qrRotatesAt = 0,
  qrBusy = false;
const app = document.getElementById("app");
const routeInfo = () => {
  const [path, query = ""] = (location.hash.slice(2) || "").split("?");
  return { path, params: new URLSearchParams(query) };
};
const go = (path) => {
  location.hash = `#/${path}`;
};
const home = () =>
  sessionState.profile?.role === "ADMIN" &&
  sessionState.profile.membership_status === "active"
    ? "admin"
    : "dashboard";
function bogotaDateTimeInput(value) {
  if (!value) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Bogota",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(value))
      .map(({ type, value: part }) => [type, part]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}
function stopSync() {
  unsubscribe?.();
  unsubscribe = null;
  subscribedId = null;
}
function stopRobotMonitor() {
  if (robotMonitorTimer) clearInterval(robotMonitorTimer);
  robotMonitorTimer = null;
}
async function refreshRobotMonitor() {
  if (robotMonitorBusy || routeInfo().path !== "admin/robots") return;
  robotMonitorBusy = true;
  try {
    if (sessionState.mode === "demo" && !(backendUrl && memoryToken.get())) {
      data.robot_monitor = await publicMonitor(
        "Estás en DEMO: aquí ves solo si el robot está conectado. Para su cámara, voz y decisiones, cierra sesión y entra con tu cuenta ADMIN real (Mi membresía).",
      );
    } else {
      data.robot_monitor = await api.robotMonitor();
    }
    markAgibot(data.robot_monitor.agibot_connected === true);
  } catch (err) {
    data.robot_monitor = await publicMonitor(
      `No se pudo abrir el monitor completo: ${readableError(err)}`,
    );
  } finally {
    robotMonitorBusy = false;
  }
  if (routeInfo().path === "admin/robots") {
    const panel = document.querySelector(".admin-panel");
    if (!panel) return;
    // Conserva el <img> MJPEG abierto para no reconectar el stream cada 3 s.
    const oldStream = panel.querySelector("[data-robot-stream]");
    const sameRobot =
      panel.querySelector("[data-robot-monitor]")?.dataset.robotId ===
      (data.robot_monitor.robot_id || "");
    panel.innerHTML = pages.adminRobotMonitor(data.robot_monitor);
    const newStream = panel.querySelector("[data-robot-stream]");
    if (oldStream?.getAttribute("src") && newStream && sameRobot && !oldStream.dataset.failed)
      newStream.replaceWith(oldStream);
    else if (newStream) newStream.src = newStream.dataset.src; // una sola conexión por stream
    hydrate();
    revealRoutes(panel);
  }
}
// Estado público (sin sesión): solo conexión de los robots, sin cámara ni datos.
async function publicMonitor(message) {
  if (!backendUrl)
    return {
      connected: false,
      error: "Configura VITE_BACKEND_URL y ejecuta el backend para ver el robot.",
    };
  try {
    const status = await api.robotStatus();
    const robot =
      status.robots.find((r) => r.connected && r.robot_id !== "camara-dispositivo") ||
      status.robots.find((r) => r.connected) ||
      status.robots[0];
    return {
      connected: Boolean(robot?.connected),
      agibot_connected: status.robots.some(
        (r) => r.connected && r.robot_id !== "camara-dispositivo",
      ),
      robot_id: robot?.robot_id,
      robot_name: robot?.name,
      updated_at: status.updated_at,
      camera: { ok: Boolean(robot?.camera_ok), live: false },
      microphone: { ok: Boolean(robot?.mic_ok), state: robot?.mic_state },
      robots: status.robots,
      public_only: true,
      error: message,
    };
  } catch (err) {
    return {
      connected: false,
      error: `${message} El backend no responde: ${readableError(err)}`,
    };
  }
}
function queueMonitorRefresh() {
  clearTimeout(monitorRefreshQueued);
  monitorRefreshQueued = setTimeout(refreshRobotMonitor, 250);
}
async function startMonitorChannel() {
  if (monitorChannel || !supabase || sessionState.mode === "demo") return;
  // Canal privado: la política en realtime.messages solo admite ADMIN activo.
  await supabase.realtime.setAuth();
  monitorChannel = supabase
    .channel("nclub:monitor", { config: { private: true } })
    .on("broadcast", { event: "*" }, ({ event, payload }) => {
      const live = document.querySelector("[data-live-transcript]");
      if (event === "transcript" && live && payload?.texto)
        live.textContent = `“${payload.texto}”`;
      queueMonitorRefresh();
    })
    .subscribe();
}
function stopMonitorChannel() {
  if (monitorChannel) supabase?.removeChannel(monitorChannel);
  monitorChannel = null;
}
function startRobotMonitor(path) {
  if (path !== "admin/robots") {
    stopRobotMonitor();
    stopMonitorChannel();
    return;
  }
  startMonitorChannel().catch(() => {
    /* Sin Realtime, el respaldo de 3 s mantiene el panel actualizado. */
  });
  if (!robotMonitorTimer) {
    refreshRobotMonitor();
    robotMonitorTimer = setInterval(refreshRobotMonitor, 3000);
  }
}
function paintSync() {
  const el = document.querySelector("#sync-status");
  if (el)
    el.innerHTML = `<span></span>${{ demo: "Demo local", live: "En tiempo real", polling: "Actualización cada 8 s", offline: "Sin conexión" }[syncStatus] || "Conectando"}`;
}
function startSync() {
  const key = `${sessionState.mode}:${sessionState.profile?.id}`;
  if (key === subscribedId) {
    paintSync();
    return;
  }
  stopSync();
  syncStatus = "connecting";
  subscribedId = key;
  unsubscribe = subscribe(
    () => refresh(),
    (state) => {
      syncStatus = state;
      paintSync();
    },
  );
  paintSync();
}
async function refresh() {
  if (
    refreshBusy ||
    !sessionState.profile ||
    flow?.busy ||
    document.querySelector("#modal").open
  )
    return;
  refreshBusy = true;
  try {
    data = await loadData();
    const { path } = routeInfo();
    const latest = data.access_events.find((ev) => !ev.simulation);
    if (path === "reception" && latest && latest.id !== flow?.lastEventId) {
      flow = {
        lastEventId: latest.id,
        visitor_id: latest.visitor_id,
        role: latest.role,
        access: latest.access_status,
        destination: latest.destination,
        robot_target: latest.robot_target,
        event_type: latest.event_type,
        simulation: false,
        step: 4,
        identity_confirmed: latest.access_status === "authorized",
        stage:
          latest.event_type === "vip_handoff"
            ? "Transferencia VIP"
            : "Atención actualizada",
        method: "Evento verificado del backend",
        message:
          latest.access_status === "authorized"
            ? accepted[latest.role]
            : "Solicite asistencia en recepción.",
      };
    }
    // admin/robots tiene su propia actualización y puede tener la cámara activa.
    if (!["credential", "profile", "login", "demo", "", "admin/robots"].includes(path)) {
      const y = scrollY;
      await render(false);
      scrollTo(0, y);
    }
  } catch (err) {
    const el = document.querySelector("#sync-status");
    if (el) el.innerHTML = "<span></span>Sin conexión";
  } finally {
    refreshBusy = false;
  }
}

async function render(scroll = true) {
  const generation = ++renderId;
  stopQrRotation();
  const { path, params } = routeInfo();
  if (path !== "admin/robots" && deviceLabActive()) stopDeviceLab();
  if (flow?.busy && path !== "reception") {
    flow = { ...flow, busy: false, cancelled: true };
  }
  try {
    if (path === "") {
      app.innerHTML = pages.landing();
    } else if (path === "ruta") {
      stopRobotMonitor();
      stopMonitorChannel();
      app.innerHTML = await routePage(params, backendUrl);
    } else if (path === "login" || path === "demo") {
      if (path === "demo" && !demoEnabled) {
        go("login");
        return;
      }
      app.innerHTML = pages.loginPage(path === "demo");
    } else if (path === "memberships") app.innerHTML = pages.memberships();
    else if (path === "experiences" && !sessionState.profile)
      app.innerHTML = pages.publicPage(pages.experiences(null));
    else {
      if (!canUseApp(sessionState.profile)) {
        stopSync();
        data = null;
        if (sessionState.profile) await logout();
        go("login");
        return;
      }
      const p = sessionState.profile;
      const admin = p.role === "ADMIN" && p.membership_status === "active";
      if ((path.startsWith("admin") || path === "reception") && !admin) {
        go(home());
        toast("Esta sección está reservada al equipo administrativo.", "error");
        return;
      }
      if (path === "dashboard" && admin) {
        go("admin");
        return;
      }
      if (path === "bookings" && !isMember(p)) {
        go(home());
        toast("Las reservas están disponibles para miembros activos.", "error");
        return;
      }
      if (path === "map" && !isMember(p)) {
        go(home());
        toast(
          "El mapa del club está disponible para miembros activos.",
          "error",
        );
        return;
      }
      if (!data) {
        app.innerHTML =
          '<main id="main" class="page-loading">' +
          icon("loader-circle") +
          "Preparando tu experiencia…</main>";
        hydrate();
        data = await loadData();
      }
      if (generation !== renderId) return;
      let content;
      if (path === "dashboard")
        content = pages.dashboard(sessionState.profile, data);
      else if (path === "bookings") content = pages.bookings(p, data, params);
      else if (path === "map") content = clubMapPage(p, data, params);
      else if (path === "experiences") content = pages.experiences(p);
      else if (path === "credential") content = pages.credential(p);
      else if (path === "history") content = pages.history(p, data);
      else if (path === "profile") content = pages.profile(p);
      else if (path === "reception") content = pages.reception(data, flow);
      else if (path === "admin" || path.startsWith("admin/"))
        content = pages.adminPage(path.split("/")[1], data);
      else
        content = empty(
          "Este rincón aún no está disponible",
          "Vuelve al inicio y continúa explorando tu club.",
          `<a class="button primary" href="#/${home()}">Mi club</a>`,
        );
      app.innerHTML = pages.shell(content, path, p);
      startSync();
      startRobotMonitor(path);
    }
    hydrate();
    if (path === "map") revealMapRoute();
    if (scroll) window.scrollTo({ top: 0, behavior: "instant" });
    if (path === "credential") refreshQr();
    if (path === "reception" && flow?.route?.steps && !flow.busy)
      await drawLinkQR(shareUrlFor(flow.route), "route-qr");
    revealRoutes();
  } catch (err) {
    app.innerHTML = `<main id="main" class="page-error">${icon("alert-circle")}<span class="eyebrow">N Club</span><h1>No pudimos preparar tu experiencia.</h1><p>${e(readableError(err))}</p><button class="button primary" data-action="retry">Intentar de nuevo</button><a href="#/login" class="button outline">Volver</a></main>`;
    hydrate();
  }
}
async function reload(scroll = false) {
  data = await loadData();
  await render(scroll);
}
async function withButton(button, work) {
  if (button?.disabled) return;
  const original = button?.innerHTML;
  if (button) {
    button.disabled = true;
    button.classList.add("is-loading");
    button.innerHTML = icon("loader-circle") + " Un momento…";
    hydrate();
  }
  try {
    await work();
  } catch (err) {
    toast(readableError(err), "error");
  } finally {
    if (button?.isConnected) {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.innerHTML = original;
      hydrate();
    }
  }
}

function stopQrRotation() {
  if (qrTimer) clearInterval(qrTimer);
  qrTimer = null;
  qrRotatesAt = 0;
}

function paintQrStatus() {
  const copy = document.querySelector("#qr-expiry-copy");
  const bar = document.querySelector("#qr-progress");
  if (!copy || !qrRotatesAt) return;
  const remaining = Math.max(0, qrRotatesAt - Date.now());
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  copy.textContent = `Se renueva automáticamente en ${minutes}:${String(seconds).padStart(2, "0")}`;
  if (bar)
    bar.style.transform = `scaleX(${Math.min(1, 1 - remaining / QR_ROTATION_MS)})`;
}

function startQrRotation(generation) {
  if (qrTimer) clearInterval(qrTimer);
  qrTimer = setInterval(() => {
    if (generation !== renderId || routeInfo().path !== "credential") {
      stopQrRotation();
      return;
    }
    if (Date.now() >= qrRotatesAt) {
      if (!qrBusy) refreshQr();
      return;
    }
    paintQrStatus();
  }, 1000);
}

async function refreshQr({ manual = false } = {}) {
  const generation = renderId;
  const canvas = document.querySelector("#credential-qr");
  if (qrBusy || !canvas || routeInfo().path !== "credential") return;
  const placeholder = document.querySelector("#qr-placeholder");
  const copy = document.querySelector("#qr-expiry-copy");
  const retry = document.querySelector("#retry-qr");
  const download = document.querySelector("#download-qr");
  const stage = document.querySelector(".qr-stage");
  const hasQr = !canvas.classList.contains("hidden");
  qrBusy = true;
  retry?.classList.add("hidden");
  if (hasQr) {
    stage?.classList.add("is-rotating");
    if (copy) copy.textContent = "Renovando tu QR…";
  } else {
    placeholder?.classList.remove("hidden", "is-error");
    if (placeholder)
      placeholder.innerHTML = `${icon("loader-circle")}<p>Preparando tu QR seguro…</p>`;
    if (copy) copy.textContent = "Generando tu credencial…";
  }
  try {
    const result = await issueCredential();
    if (
      generation !== renderId ||
      routeInfo().path !== "credential" ||
      !canvas.isConnected
    )
      return;
    await drawQR(result.token);
    placeholder?.classList.add("hidden");
    canvas.classList.remove("hidden");
    download?.classList.remove("hidden");
    retry?.classList.add("hidden");
    qrRotatesAt = Date.now() + QR_ROTATION_MS;
    paintQrStatus();
    startQrRotation(generation);
  } catch (err) {
    stopQrRotation();
    if (generation !== renderId || routeInfo().path !== "credential") return;
    if (!hasQr && placeholder) {
      placeholder.classList.add("is-error");
      placeholder.innerHTML = `${icon("alert-circle")}<p>No pudimos preparar tu QR.</p>`;
    }
    if (copy)
      copy.textContent = hasQr
        ? "No pudimos renovar tu QR. El anterior sigue visible."
        : "Revisa tu conexión e inténtalo de nuevo.";
    retry?.classList.remove("hidden");
    if (manual) toast(readableError(err), "error");
  } finally {
    stage?.classList.remove("is-rotating");
    qrBusy = false;
    if (generation !== renderId && routeInfo().path === "credential")
      refreshQr();
  }
}

let bookingContext = null,
  availabilityVersion = 0;
async function openBooking(serviceId, reservationId) {
  const service = data.services.find((s) => s.id === serviceId);
  if (!service || !canBook(sessionState.profile, service))
    throw new Error("Tu membresía no incluye este servicio.");
  const reservation = data.reservations.find((r) => r.id === reservationId);
  bookingContext = { service, reservation };
  modal(
    reservation ? "Cambiar fecha y hora" : "Elige fecha y hora",
    `<div class="modal-service"><img src="${e(service.image || images[service.category === "golf" ? "course" : service.category])}" alt="${e(service.name)}"/><div><h3>${e(service.name)}</h3><p>Una experiencia de 60 minutos · Hora Colombia</p></div></div><form id="booking-form"><div class="modal-date"><label>Fecha de tu experiencia<input type="date" id="booking-date" name="date" min="${today()}" max="${dateAfter(90)}" value="${reservation?.reservation_date || dateAfter()}" required/></label></div><p class="slot-label">Elige tu horario</p><div id="booking-slots" class="time-slots"><p>Consultando disponibilidad…</p></div><p class="form-error" id="booking-error" role="alert"></p><div class="booking-summary"><span>Tu experiencia N Club</span><strong>Incluida según tu membresía</strong></div><button class="button primary full" type="submit">${reservation ? "Guardar cambio" : "Confirmar reserva"} ${icon("arrow-up-right")}</button></form>`,
  );
  await updateSlots();
}
async function updateSlots() {
  if (!bookingContext) return;
  const version = ++availabilityVersion;
  const date = document.querySelector("#booking-date")?.value;
  if (!date) return;
  const container = document.getElementById("booking-slots");
  container.innerHTML = "<p>Consultando disponibilidad…</p>";
  try {
    const busy = await availability(bookingContext.service.id, date);
    if (version !== availabilityVersion || !container.isConnected) return;
    const own = bookingContext.reservation;
    container.innerHTML = slots
      .map((time) => {
        const past = new Date(`${date}T${time}:00-05:00`) <= new Date();
        const occupied =
          busy.some(
            (r) =>
              r.start_time.slice(0, 5) <= time && r.end_time.slice(0, 5) > time,
          ) &&
          !(
            own &&
            own.reservation_date === date &&
            own.start_time.slice(0, 5) === time
          );
        const conflict = data.reservations.some(
          (r) =>
            r.user_id === sessionState.profile.id &&
            r.id !== own?.id &&
            r.status === "confirmed" &&
            r.reservation_date === date &&
            r.start_time.slice(0, 5) === time,
        );
        return `<label class="time-slot"><input type="radio" name="time" value="${time}" required ${past || occupied || conflict ? "disabled" : ""} ${!past && !occupied && !conflict && own?.start_time.slice(0, 5) === time ? "checked" : ""}/><span>${time}</span></label>`;
      })
      .join("");
  } catch (err) {
    container.innerHTML = `<p class="form-error">${e(readableError(err))}</p>`;
  }
}
const photoFields = (required) =>
  `<label>Foto del rostro<input name="photo" type="file" accept="image/*" capture="user" ${required ? "required" : ""} /></label><p class="form-hint">Rostro de frente, bien iluminado y una sola persona. Se recodifica sin metadatos y se guarda en Storage privado.</p><label class="consent-check"><input name="consent" type="checkbox" required /> El titular autorizó el uso de su foto para reconocimiento facial en la recepción del club.</label>`;
const voiceFields = (required) =>
  `<label>Grabación de voz<input name="voice" type="file" accept="audio/wav,.wav" ${required ? "required" : ""} /></label><button type="button" class="button outline" data-action="record-voice">${icon("mic")} Grabar muestra de 8 segundos</button><p class="form-hint" data-voice-status role="status">Puedes subir un WAV mono de 16 kHz y 16 bits o grabar una frase natural, sin música ni otras voces.</p><label class="consent-check"><input name="voice_consent" type="checkbox" required /> El titular autorizó registrar y verificar su voz para confirmar su identidad en recepción.</label>`;
async function recordVoiceSample(button) {
  const form = button.closest("form");
  const input = form?.querySelector('[name="voice"]');
  const status = button.closest("[data-sample-row]")?.querySelector("[data-voice-status]") || form?.querySelector("[data-voice-status]");
  if (!form?.querySelector('[name="voice_consent"]').checked)
    throw new Error("Confirma el consentimiento para grabar la muestra de voz.");
  if (!window.isSecureContext && location.hostname !== "localhost" && location.hostname !== "127.0.0.1")
    throw new Error("El navegador bloquea el microfono en HTTP por IP local. Abre el panel en HTTPS o en localhost, o sube un WAV mono de 16 kHz.");
  if (!navigator.mediaDevices?.getUserMedia || !(window.AudioContext || window.webkitAudioContext))
    throw new Error("Este navegador no admite grabar audio. Sube un archivo WAV mono de 16 kHz.");
  button.disabled = true;
  status.textContent = "Solicitando acceso al micrófono…";
  let stream;
  let context;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    context = new AudioContextClass({ sampleRate: 16000 });
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const mute = context.createGain();
    mute.gain.value = 0;
    const chunks = [];
    processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(mute);
    mute.connect(context.destination);
    status.textContent = "Grabando. Di una frase natural con voz clara…";
    await new Promise((resolve) => setTimeout(resolve, 8000));
    processor.disconnect();
    source.disconnect();
    mute.disconnect();
    const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const captured = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) { captured.set(chunk, offset); offset += chunk.length; }
    const rms = Math.sqrt(captured.reduce((sum, sample) => sum + sample * sample, 0) / Math.max(1, captured.length));
    if (rms < 0.003) throw new Error("No se oyó suficiente voz. Acércate al micrófono e inténtalo de nuevo.");
    const targetRate = 16000;
    const length = Math.floor(captured.length * targetRate / context.sampleRate);
    const wav = new ArrayBuffer(44 + length * 2);
    const view = new DataView(wav);
    const write = (at, value) => [...value].forEach((char, i) => view.setUint8(at + i, char.charCodeAt(0)));
    write(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); write(8, "WAVE");
    write(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, targetRate, true);
    view.setUint32(28, targetRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    write(36, "data"); view.setUint32(40, length * 2, true);
    for (let i = 0; i < length; i++) {
      const position = i * context.sampleRate / targetRate;
      const left = Math.floor(position);
      const fraction = position - left;
      const sample = (captured[left] || 0) * (1 - fraction) + (captured[Math.min(left + 1, captured.length - 1)] || 0) * fraction;
      view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767), true);
    }
    const file = new File([wav], "muestra-voz.wav", { type: "audio/wav" });
    if (input) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    }
    status.textContent = "Muestra grabada y lista (WAV mono, 16 kHz).";
    return file;
  } finally {
    stream?.getTracks().forEach((track) => track.stop());
    await context?.close();
    button.disabled = false;
  }
}
function appendPersonFields(form, profile = {}, required = false) {
  const container = form.querySelector(".form-grid") || form;
  const type = profile.document_type || "";
  container.insertAdjacentHTML(
    "beforeend",
    `<label>Tipo de documento<select name="tipo_documento" ${required ? "required" : ""}><option value="" ${!type ? "selected" : ""}>Selecciona</option>${[["CC", "Cédula de ciudadanía"], ["CE", "Cédula de extranjería"], ["PASAPORTE", "Pasaporte"], ["OTRO", "Otro"]].map(([v, label]) => `<option value="${v}" ${type === v ? "selected" : ""}>${label}</option>`).join("")}</select></label><label>Número de documento<input name="numero_documento" value="${e(profile.document_number || "")}" minlength="5" maxlength="30" ${required ? "required" : ""} autocomplete="off" /></label><label>Teléfono<input name="telefono" type="tel" value="${e(profile.phone || "")}" maxlength="30" autocomplete="tel" /></label><label>Correo<input name="email" type="email" value="${e(profile.email || "")}" maxlength="120" autocomplete="email" /></label><label>Empresa o cargo<input name="cargo" value="${e(profile.position || "")}" maxlength="100" /></label>${["VIP", "REGULAR"].includes(profile.role) ? `<label>Vigente hasta<input name="vigencia_hasta" type="date" value="${e(profile.membership_expires_at?.slice(0, 10) || "")}" /></label>` : ""}`,
  );
}
function backendNotice() {
  if (!backendUrl)
    return `<div class="notice">${icon("alert-circle")}<p>Configure VITE_BACKEND_URL: la foto y el reconocimiento facial los procesa FastAPI.</p></div>`;
  if (sessionState.mode === "demo" && !memoryToken.get())
    return `<div class="notice">${icon("alert-circle")}<p>En DEMO, primero escriba el token del backend en modo memoria en Admin → Robots.</p></div>`;
  return "";
}
function openMember() {
  const until = new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10);
  modal(
    "Nuevo miembro.",
    `<form id="member-form">${backendNotice()}<label>Nombre completo<input name="nombre" minlength="3" maxlength="100" required autocomplete="off" /></label><label>Membresía<select name="categoria"><option value="REGULAR">Miembro regular</option><option value="VIP">VIP · Black</option></select></label><label>Tipo de documento<select name="tipo_documento" required><option value="CC">Cédula de ciudadanía</option><option value="CE">Cédula de extranjería</option><option value="PASAPORTE">Pasaporte</option><option value="OTRO">Otro</option></select></label><label>Número de documento<input name="numero_documento" minlength="5" maxlength="30" required autocomplete="off" /></label><label>Teléfono<input name="telefono" type="tel" maxlength="30" autocomplete="tel" /></label><label>Correo (opcional)<input name="email" type="email" maxlength="120" autocomplete="email" /></label><label>Vigente hasta<input name="vigencia_hasta" type="date" min="${today()}" value="${until}" required /></label>${photoFields(false)}<p class="form-error" role="alert"></p><button class="button primary full">${icon("check")} Crear miembro</button></form>`,
  );
  const form = document.querySelector("#member-form");
  form.querySelector('[name="photo"]').required = true;
  form.insertAdjacentHTML("beforeend", voiceFields(true));
}
function openPhoto(id, name) {
  modal(
    "Foto de reconocimiento.",
    `<form id="photo-form" data-id="${e(id)}">${backendNotice()}<p class="confirm-copy">${e(name)}: la foto se usará para reconocer su rostro en recepción. El acceso seguirá dependiendo de su credencial y membresía.</p>${photoFields(true)}<p class="form-error" role="alert"></p><button class="button primary full">${icon("camera")} Subir foto</button></form>`,
  );
}
function openVoice(id, name) {
  modal(
    "Voz de reconocimiento.",
    `<form id="voice-form" data-id="${e(id)}">${backendNotice()}<p class="confirm-copy">${e(name)}: se guardará una muestra en Storage privado y se comparará en recepción. El audio de las visitas solo se conserva como evidencia con consentimiento adicional y STORE_EVIDENCE activado.</p>${voiceFields(true)}<p class="form-error" role="alert"></p><button class="button primary full">${icon("mic")} Registrar voz</button></form>`,
  );
}
const enrollmentPrompts = (name) => [
  `Mi nombre es ${name}. Soy parte de N Club y hoy vengo a disfrutar de mis actividades.`,
  "Por favor, ayudenme a confirmar mi identidad para continuar con mi visita.",
  "Estoy en recepcion de N Club para validar mi membresia y dirigirme a mi actividad.",
];
const verificationPrompt = "Quisiera confirmar mi ingreso y consultar mi proxima actividad en el club.";
function renderBiometrics(id, name, data = { photos: [], voices: [] }) {
  const photoCards = data.photos.map((photo) => `<a class="biometric-photo" href="${e(photo.url)}" target="_blank" rel="noreferrer"><img src="${e(photo.url)}" alt="Foto de reconocimiento de ${e(name)}" loading="lazy"/><span>${e(photo.name)}</span></a>`).join("");
  const voiceBySample = new Map(data.voices.filter((voice) => voice.sample_id).map((voice) => [voice.sample_id, voice]));
  const samples = enrollmentPrompts(name).map((phrase, index) => {
    const sampleId = index + 1;
    const voice = voiceBySample.get(sampleId);
    return `<article class="voice-sample" data-sample-row="${sampleId}"><div><span class="eyebrow">Frase ${sampleId} ${voice ? "· Guardada" : "· Pendiente"}</span><p>${e(phrase)}</p></div>${voice ? `<audio controls preload="none" src="${e(voice.url)}">Audio no disponible</audio>` : ""}<p class="form-hint" data-voice-status role="status">${voice ? "Muestra lista para el reconocimiento." : "Lee la frase con voz natural, sin musica ni otras voces."}</p><button type="button" class="button outline" data-action="record-enrollment-voice" data-id="${e(id)}" data-name="${e(name)}" data-sample="${sampleId}">${icon("mic")} ${voice ? "Volver a grabar" : "Grabar frase"}</button></article>`;
  }).join("");
  const legacy = data.voices.filter((voice) => !voice.sample_id).map((voice) => `<article class="voice-sample"><span class="eyebrow">Muestra anterior</span><audio controls preload="none" src="${e(voice.url)}">Audio no disponible</audio><small>${e(voice.name)}</small></article>`).join("");
  modal("Biometria de persona", `<div class="biometric-panel" data-persona-id="${e(id)}" data-persona-name="${e(name)}"><p class="confirm-copy">${e(name)} · La foto y las tres frases se guardan en Storage privado. La cuarta frase sirve para probar la coincidencia y no se conserva.</p><section class="biometric-block"><div class="biometric-heading"><h3>Foto de reconocimiento</h3><button type="button" class="button outline" data-action="upload-photo" data-id="${e(id)}" data-name="${e(name)}">${icon("camera")} Agregar foto</button></div><div class="biometric-photos">${photoCards || `<p class="form-hint">Aun no hay una foto registrada.</p>`}</div></section><form class="biometric-form" data-id="${e(id)}"><label class="consent-check"><input name="voice_consent" type="checkbox" required /> La persona autorizo registrar y verificar su voz.</label><section class="biometric-block"><div class="biometric-heading"><h3>Entrenamiento de voz</h3><span>${voiceBySample.size}/3 frases</span></div><p class="form-hint">Graba las tres frases, una por una. Cada audio se usa como referencia para reconocer la voz en recepcion.</p><div class="voice-samples">${samples}${legacy}</div></section><section class="biometric-block" data-sample-row="test"><div class="biometric-heading"><h3>Probar reconocimiento</h3></div><p class="voice-prompt">${e(verificationPrompt)}</p><input type="file" name="voice" accept="audio/wav,.wav" hidden/><p class="form-hint" data-voice-status role="status">Graba la frase para comparar con las muestras guardadas.</p><button type="button" class="button outline" data-action="record-test-voice">${icon("mic")} Grabar frase de prueba</button><button type="button" class="button primary full" data-action="verify-voice" data-id="${e(id)}">${icon("scan-eye")} Reconocer voz</button><div class="voice-result" data-voice-result role="status"></div></section></form></div>`, true);
}
async function openBiometrics(id, name) {
  try {
    renderBiometrics(id, name, await api.personaBiometrics(id));
  } catch (err) {
    toast(`No se pudo cargar la biometria: ${readableError(err)}`, "error");
  }
}
async function refreshBiometrics(id, name) {
  renderBiometrics(id, name, await api.personaBiometrics(id));
}

async function submitMember(form, values) {
  const file = form.querySelector('[name="photo"]').files[0];
  const voice = form.querySelector('[name="voice"]').files[0];
  const created = await api.createMember({
    nombre: values.nombre.trim(),
    categoria: values.categoria,
    vigencia_hasta: values.vigencia_hasta,
    email: values.email || null,
    telefono: values.telefono || null,
    tipo_documento: values.tipo_documento,
    numero_documento: values.numero_documento,
  });
  const feedback = [];
  try {
    const result = await api.uploadPhoto(created.persona_id, await photoToJpeg(file));
    feedback.push(result.enrolled ? "rostro registrado" : "rostro pendiente");
  } catch (err) { feedback.push(`rostro pendiente: ${readableError(err)}`); }
  try {
    await api.uploadVoice(created.persona_id, voice);
    feedback.push("voz registrada para verificación");
  } catch (err) { feedback.push(`voz pendiente: ${readableError(err)}`); }
  if (sessionState.mode === "demo") {
    // Copia visible en la lista DEMO; la autoridad es el backend en memoria.
    const d = readDemo();
    d.profiles.push({
      id: created.persona_id,
      full_name: created.nombre,
      role: created.categoria,
      membership_status: "active",
      public_id: created.persona_id,
      created_at: new Date().toISOString(),
      email: values.email || null,
      phone: values.telefono || null,
      document_type: values.tipo_documento,
      document_number: values.numero_documento.replace(/[^a-z0-9]/gi, "").toUpperCase(),
      membership_expires_at: `${values.vigencia_hasta}T23:59:59-05:00`,
      backend: true,
    });
    writeDemo(d);
  }
  await reload();
  await showQR(created.credential, created.nombre);
  const biometricFailure = feedback.some((item) => item.includes("pendiente"));
  toast(`Miembro ${created.persona_id} creado: ${feedback.join("; ")}.`, biometricFailure ? "error" : "success");
}
function openVisitor(type) {
  const now = dateAfter();
  modal(
    type === "GUEST"
      ? "Una invitación especial."
      : "Una autorización de trabajo.",
    `<form id="visitor-form"><div class="form-grid"><label class="span-full">Nombre completo<input name="name" required minlength="3" maxlength="100" placeholder="Nombre y apellido"/></label><label class="span-full">Tipo<select name="role" id="visitor-role"><option value="GUEST" ${type === "GUEST" ? "selected" : ""}>Invitado</option><option value="STAFF" ${type === "STAFF" ? "selected" : ""}>Turno de personal</option><option value="EXTERNAL" ${type === "EXTERNAL" ? "selected" : ""}>Trabajador externo</option></select></label><label class="span-full" id="host-field">Miembro anfitrión<select name="host_id">${data.profiles
      .filter((p) => isMember(p) && p.membership_status === "active")
      .map(
        (p) =>
          `<option value="${e(p.id)}">${e(p.full_name)} · ${roles[p.role]}</option>`,
      )
      .join(
        "",
      )}</select></label><label class="span-full" id="company-field">Empresa<input name="company" maxlength="100" placeholder="Empresa o N Club World"/></label><label>Desde (Colombia)<input type="datetime-local" name="valid_from" value="${now}T08:00" required/></label><label>Hasta (Colombia)<input type="datetime-local" name="valid_until" value="${now}T18:00" required/></label><label class="span-full">Zona autorizada<select name="destination" id="visitor-zone"></select></label></div><p class="form-error" id="visitor-error" role="alert"></p><div class="notice">${icon("shield-check")}<p>El token será temporal. Una invitación u orden no concede acceso a otras zonas.</p></div><button class="button primary full">Crear y generar QR ${icon("qr-code")}</button></form>`,
    true,
  );
  appendPersonFields(document.querySelector("#visitor-form"), {}, true);
  updateVisitorFields();
}
function updateVisitorFields() {
  const role = document.querySelector("#visitor-role")?.value;
  if (!role) return;
  document
    .querySelector("#host-field")
      .classList.toggle("hidden", role !== "GUEST");
  document
    .querySelector("#company-field")
    .classList.toggle("hidden", role === "GUEST");
  document.querySelector('[name="company"]').required = role !== "GUEST";
  const zones =
    role === "GUEST"
      ? [
          ["RESTAURANT", "Restaurante"],
          ["GOLF_RECEPTION", "Recepción de golf"],
        ]
      : role === "STAFF"
        ? [
            ["KITCHEN", "Cocina"],
            ["RECEPTION", "Recepción"],
            ["GOLF_OPERATIONS", "Operación de golf"],
          ]
        : [
            ["MAINTENANCE", "Mantenimiento"],
            ["SERVICE_ENTRANCE", "Entrada de servicio"],
          ];
  document.querySelector("#visitor-zone").innerHTML = zones
    .map(([v, l]) => `<option value="${v}">${l}</option>`)
    .join("");
}
async function showQR(result, name) {
  modal(
    "Tu credencial está lista.",
    `<div class="qr-modal"><span class="eyebrow">${sessionState.mode === "demo" ? "Demo, sin acceso real" : "Token temporal de verificación"}</span><h3>${e(name)}</h3><canvas id="visitor-qr" aria-label="Credencial temporal QR"></canvas><p>Vence: ${e(new Date(result.expires_at).toLocaleString("es-CO", { timeZone: "America/Bogota" }))}</p><button class="button primary full" data-action="download-visitor-qr">${icon("download")} Descargar credencial</button><div class="notice">${icon("shield-check")}<p>Comparte el QR únicamente con su titular. Recepción verificará su vigencia y permisos.</p></div></div>`,
  );
  await drawQR(result.token, "visitor-qr");
}

const greetings = {
  VIP: "Bienvenida a N Club World. Es un placer recibirla nuevamente.",
  REGULAR:
    "Bienvenido a N Club World. Por favor, presente su credencial para verificar su membresía.",
  GUEST: "Bienvenido a N Club World. Por favor, presente su invitación.",
  STAFF: "Bienvenido. Por favor, presente su identificación de personal.",
  EXTERNAL:
    "Bienvenido. Para continuar, necesitamos verificar su autorización de trabajo.",
};
const accepted = {
  VIP: "Su membresía VIP está activa. Mi compañero estará encantado de brindarle atención personalizada.",
  REGULAR:
    "Su acceso ha sido autorizado. Su reserva se encuentra disponible. Le indicaré cómo llegar.",
  GUEST:
    "Su invitación ha sido confirmada. Su anfitrión lo espera en el área asignada.",
  STAFF: "Su turno ha sido verificado. Puede dirigirse a su zona de trabajo.",
  EXTERNAL:
    "Su orden de trabajo está vigente. Puede dirigirse únicamente al área asignada.",
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const stageFor = (access) =>
  ({
    authorized: "Acceso autorizado",
    pending: "Acompañamiento requerido",
    review: "Revisión requerida",
  })[access] || "Acceso denegado";
function messageFor(decision) {
  if (decision.access === "authorized") return accepted[decision.role];
  if (decision.access === "pending")
    return "Su orden de trabajo está vigente. Espere a su acompañante en la recepción de proveedores.";
  if (decision.access === "review")
    return "Necesitamos una verificación adicional. Nuestro equipo de recepción le acompañará.";
  return "No ha sido posible validar su autorización. Por favor, solicite asistencia en recepción.";
}
// Sin backend: la ruta se calcula en el navegador con el mismo grafo (DEMO).
function demoRoute(decision) {
  if (!["authorized", "pending"].includes(decision.access) || !decision.destination)
    return null;
  try {
    return computeRoute(roleToCategory[decision.role], decision.destination, {
      escort: decision.role === "EXTERNAL",
    });
  } catch (err) {
    return { error: readableError(err), destination: decision.destination };
  }
}
async function simulate(role) {
  if (sessionState.profile?.role !== "ADMIN" || flow?.busy) return;
  const outcome =
    document.querySelector("#simulation-outcome")?.value || "authorized";
  const profile = data.profiles.find((p) => p.role === role);
  const run = uid();
  flow = {
    run,
    busy: true,
    simulation: true,
    step: 0,
    stage: "Visitante detectado",
    role,
    visitor_id: profile?.id,
    method: "Credencial QR · DEMO",
    message: greetings[role],
    robot_target: "robot1",
    requested_outcome: outcome,
  };
  const alive = () =>
    flow?.run === run && !flow.cancelled && routeInfo().path === "reception";
  await render(false);
  for (const [step, stage, message] of [
    [1, "Identificando", "Verificando la identidad del visitante…"],
    [2, "Verificando credencial", "Consultando vigencia y credencial…"],
    [
      3,
      "Validando permisos",
      "Evaluando categoría, horario y destino permitido…",
    ],
  ]) {
    await pause(650);
    if (!alive()) return;
    Object.assign(flow, { step, stage, message });
    await render(false);
  }
  let decision,
    source = "Demo local",
    context = null;
  if (backendUrl && sessionState.mode !== "demo") {
    try {
      await api.health();
      decision = validateDecision(
        await api.check({
          visitor_id: profile?.id || null,
          scenario: role,
          simulation: true,
          requested_outcome: outcome,
        }),
        true,
      );
      source = "DEMO BACKEND";
      if (
        decision.event_type === "vip_handoff" &&
        decision.access === "authorized"
      )
        context = await api.vipContext(decision.visitor_id);
    } catch (err) {
      if (!alive()) return;
      toast(
        `Backend no evaluó el escenario: ${readableError(err)} Resultado ficticio DEMO.`,
        "error",
      );
    }
  }
  if (!alive()) return;
  if (!decision) {
    // Fresh, isolated fixture for the regular scenario: a valid booking at the demo arrival time.
    const fixtures = sessionState.mode === "demo" ? readDemo() : seed();
    let person = fixtures.profiles.find((p) => p.role === role);
    if (role === "REGULAR") {
      fixtures.reservations = fixtures.reservations.filter(
        (r) => r.user_id !== person.id,
      );
      fixtures.reservations.push({
        id: uid(),
        user_id: person.id,
        service_id: fixtures.services[0].id,
        reservation_date: today(),
        start_time: "00:00",
        end_time: "23:59:59",
        status: "confirmed",
      });
    }
    decision = {
      ...evaluateDemo(person, fixtures, outcome),
      visitor_name: person.full_name,
    };
    if (role === "REGULAR")
      decision.reason =
        "Escenario ficticio: reserva válida a la hora de llegada DEMO. No modifica tus reservas.";
  }
  Object.assign(flow, decision, {
    source,
    step: 4,
    identity_confirmed: ["authorized", "pending"].includes(decision.access),
    busy: false,
    stage: stageFor(decision.access),
    message: messageFor(decision),
    route: decision.route ?? demoRoute(decision),
  });
  if (decision.access === "authorized" && decision.role === "REGULAR")
    flow.reservation_label = "Cancha 1 · Hora de llegada DEMO";
  if (decision.access === "authorized" && decision.role === "VIP")
    flow.reservation_label =
      context?.reservation_label || "Cancha 2 · 16:00 · DEMO";
  if (sessionState.mode === "demo") {
    appendDemoEvent(decision);
    data = await loadData();
  }
  await render(false);
  if (
    decision.event_type === "vip_handoff" &&
    decision.access === "authorized"
  ) {
    flow.busy = true;
    await pause(1100);
    if (!alive()) return;
    Object.assign(flow, {
      busy: false,
      stage: "Transferencia VIP completada",
      message: `Bienvenida a su experiencia exclusiva. ${context?.message || "Tiene una reserva en la cancha 2 a las 4:00 p. m. ¿Desea consultar nuestros servicios premium?"}${source === "Demo local" ? " · Contexto simulado" : ""}`,
    });
    await render(false);
  }
}

document.addEventListener("click", async (event) => {
  if (event.target.closest(".mobile-menu a"))
    event.target.closest("details").open = false;
  document.querySelectorAll(".mobile-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
  if (event.target.closest(".skip-link")) {
    event.preventDefault();
    const main = document.querySelector("main");
    if (main) {
      main.tabIndex = -1;
      main.focus();
      main.scrollIntoView();
    }
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "close-modal") {
    closeModal();
    return;
  }
  if (action === "toggle-password") {
    const input = document.querySelector('[name="password"]');
    input.type = input.type === "password" ? "text" : "password";
    button.setAttribute(
      "aria-label",
      input.type === "password" ? "Mostrar contraseña" : "Ocultar contraseña",
    );
    return;
  }
  if (action === "simulate") {
    await simulate(button.dataset.role);
    return;
  }
  if (action === "map-destination") {
    selectMapDestination(button.dataset.destination);
    return;
  }
  if (action === "lab-start") {
    try {
      await startDeviceLab();
    } catch (err) {
      stopDeviceLab();
      toast(readableError(err), "error");
    }
    return;
  }
  if (action === "lab-stop") {
    stopDeviceLab();
    return;
  }
  if (action === "lab-mic") {
    toggleLabMic(button);
    return;
  }
  if (action === "record-voice") {
    try {
      await recordVoiceSample(button);
    } catch (err) {
      const status = button.closest("form")?.querySelector("[data-voice-status]");
      if (status) status.textContent = readableError(err);
      toast(readableError(err), "error");
      button.disabled = false;
    }
    return;
  }
  if (action === "record-enrollment-voice") {
    const form = button.closest("form");
    const row = button.closest("[data-sample-row]");
    const status = row?.querySelector("[data-voice-status]");
    try {
      if (!form?.querySelector('[name="voice_consent"]')?.checked) throw new Error("Confirma el consentimiento antes de grabar.");
      const file = await recordVoiceSample(button);
      status.textContent = "Guardando muestra privada…";
      await api.uploadVoice(button.dataset.id, file, Number(button.dataset.sample));
      await refreshBiometrics(button.dataset.id, button.dataset.name);
      toast(`Frase ${button.dataset.sample} guardada para el reconocimiento.`);
    } catch (err) {
      if (status) status.textContent = readableError(err);
      toast(readableError(err), "error");
      button.disabled = false;
    }
    return;
  }
  if (action === "record-test-voice") {
    try {
      const form = button.closest("form");
      if (!form?.querySelector('[name="voice_consent"]')?.checked) throw new Error("Confirma el consentimiento antes de grabar.");
      await recordVoiceSample(button);
    } catch (err) {
      const status = button.closest("[data-sample-row]")?.querySelector("[data-voice-status]");
      if (status) status.textContent = readableError(err);
      toast(readableError(err), "error");
      button.disabled = false;
    }
    return;
  }
  if (action === "verify-voice") {
    const panel = button.closest(".biometric-panel");
    const form = button.closest("form");
    const file = form?.querySelector('[name="voice"]')?.files[0];
    const result = form?.querySelector("[data-voice-result]");
    try {
      if (!form?.querySelector('[name="voice_consent"]')?.checked) throw new Error("Confirma el consentimiento antes de hacer la prueba.");
      if (!file) throw new Error("Graba primero la frase de prueba.");
      button.disabled = true;
      result.textContent = "Comparando la voz con las muestras guardadas…";
      const comparison = await api.verifyVoice(panel.dataset.personaId, file);
      result.textContent = comparison.matched
        ? `Coincidencia de voz: reconocida (${comparison.matches}/${comparison.samples}; similitud ${comparison.similarity.toFixed(2)}).`
        : `Sin coincidencia suficiente (${comparison.matches}/${comparison.samples}; similitud ${comparison.similarity.toFixed(2)}).`;
      result.classList.toggle("is-match", comparison.matched);
      result.classList.toggle("is-no-match", !comparison.matched);
    } catch (err) {
      if (result) result.textContent = readableError(err);
      toast(readableError(err), "error");
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "biometric-add-photo") {
    openPhoto(button.dataset.id, button.dataset.name);
    return;
  }
  if (action === "generate-qr") {
    await refreshQr({ manual: true });
    return;
  }
  await withButton(button, async () => {
    if (action === "demo-login") {
      if (!demoEnabled) throw new Error("Modo DEMO deshabilitado.");
      stopSync();
      loginDemo(button.dataset.id);
      data = await loadData();
      flow = null;
      go(home());
    }
    if (action === "logout") {
      stopSync();
      await logout();
      data = null;
      flow = null;
      closeModal();
      go("");
    }
    if (action === "retry") {
      data = null;
      await render();
    }
    if (action === "book") await openBooking(button.dataset.id);
    if (action === "edit-reservation") {
      const r = data.reservations.find((r) => r.id === button.dataset.id);
      if (!r) throw new Error("Reserva no encontrada.");
      await openBooking(r.service_id, r.id);
    }
    if (action === "cancel-reservation") {
      modal(
        "¿Cambiar de planes?",
        `<p class="confirm-copy">Al cancelar, este horario quedará disponible para otros miembros. Podrás reservar una nueva experiencia cuando quieras.</p><div class="modal-actions"><button class="button outline" data-action="close-modal">Conservar reserva</button><button class="button primary" data-action="confirm-cancel" data-id="${e(button.dataset.id)}">Cancelar reserva</button></div>`,
      );
    }
    if (action === "confirm-cancel") {
      await cancel(button.dataset.id);
      closeModal();
      await reload();
      toast("Reserva cancelada. Te esperamos en tu próxima experiencia.");
    }
    if (action === "download-qr" || action === "download-visitor-qr") {
      const canvas = document.getElementById(
        action === "download-qr" ? "credential-qr" : "visitor-qr",
      );
      const a = document.createElement("a");
      a.download = `nclub-credencial${sessionState.mode === "demo" ? "-DEMO" : ""}.png`;
      a.href = canvas.toDataURL("image/png");
      a.click();
    }
    if (action === "assistance") {
      if (sessionState.mode === "demo")
        toast("DEMO · Tu solicitud de atención se ha simulado.");
      else {
        await api.assistance();
        toast("Solicitud enviada al equipo del club.");
      }
    }
    if (action === "edit-user") {
      const p = data.profiles.find((p) => p.id === button.dataset.id);
      modal(
        "Información del visitante.",
        `<form id="user-form" data-id="${e(p.id)}"><label>Nombre completo<input name="full_name" value="${e(p.full_name)}" minlength="3" maxlength="100" required/></label><label>Estado<select name="membership_status">${["active", "inactive", "suspended"].map((v) => `<option value="${v}" ${p.membership_status === v ? "selected" : ""}>${{ active: "Activo", inactive: "Inactivo", suspended: "Suspendido" }[v]}</option>`).join("")}</select></label><div class="notice">${icon("shield-check")}<p>Categoría: ${roles[p.role]}. Los cambios de rol requieren una operación privilegiada en el servidor.</p></div><button class="button primary full">Guardar cambios ${icon("check")}</button></form>`,
      );
      appendPersonFields(document.querySelector("#user-form"), p);
    }
    if (action === "new-visitor") openVisitor(button.dataset.type);
    if (action === "new-member") openMember();
    if (action === "edit-authorization") {
      const table = button.dataset.table;
      const rows = data?.[table];
      const row = rows?.find((item) => item.id === button.dataset.id);
      if (!row || !["invitations", "work_assignments"].includes(table))
        throw new Error("No se encontró la autorización para editar.");
      const person = data.profiles.find(
        (profile) => profile.id === (row.guest_id || row.worker_id),
      );
      modal(
        "Editar vigencia.",
        `<form id="authorization-dates-form" data-id="${e(row.id)}" data-table="${e(table)}"><p class="confirm-copy">Ajusta las fechas de ${e(person?.full_name || "la autorización")}. Puedes usar fechas pasadas para probar el reconocimiento de vigencias vencidas.</p><div class="form-grid"><label>Desde (Colombia)<input type="datetime-local" name="valid_from" value="${e(bogotaDateTimeInput(row.valid_from))}" required/></label><label>Hasta (Colombia)<input type="datetime-local" name="valid_until" value="${e(bogotaDateTimeInput(row.valid_until))}" required/></label></div><p class="form-error" role="alert"></p><button class="button primary full">${icon("check")} Guardar vigencia</button></form>`,
      );
    }
    if (action === "upload-photo") openPhoto(button.dataset.id, button.dataset.name);
    if (action === "upload-voice") await openBiometrics(button.dataset.id, button.dataset.name);
    if (action === "visitor-qr") {
      const backendMember = data.profiles.find((p) => p.id === button.dataset.id)?.backend;
      const result = backendMember
        ? await api.memberCredential(button.dataset.id)
        : await issueCredential(button.dataset.id);
      await showQR(
        result,
        data.profiles.find((p) => p.id === button.dataset.id)?.full_name,
      );
    }
    if (action === "revoke") {
      modal(
        "Revocar autorización.",
        `<p class="confirm-copy">La invitación o el permiso dejará de ser válido para nuevas verificaciones de acceso.</p><div class="modal-actions"><button class="button outline" data-action="close-modal">Conservar</button><button class="button primary" data-action="confirm-revoke" data-id="${e(button.dataset.id)}" data-table="${e(button.dataset.table)}">Revocar permiso</button></div>`,
      );
    }
    if (action === "confirm-revoke") {
      await revoke(button.dataset.table, button.dataset.id);
      closeModal();
      await reload();
      toast("Autorización revocada.");
    }
    if (action === "health") {
      const health = await api.health();
      const el = document.querySelector("#backend-status");
      if (el) el.innerHTML = "<span></span>Backend disponible";
      toast(`FastAPI responde: ${health.status || "OK"}.`);
    }
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".mobile-menu[open]").forEach((menu) => {
    menu.open = false;
    menu.querySelector("summary").focus();
  });
});

document.addEventListener("change", async (event) => {
  if (event.target.matches("[data-lab-voice]")) setLabVoice(event.target.checked);
  if (event.target.id === "booking-date") await updateSlots();
  if (event.target.id === "visitor-role") updateVisitorFields();
});
document.addEventListener("input", (event) => {
  if (event.target.id === "user-search") {
    const search = event.target.value.toLowerCase();
    document
      .querySelectorAll("#users-table tbody tr")
      .forEach((row) => (row.hidden = !row.dataset.search.includes(search)));
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (
    ![
      "login-form",
      "booking-form",
      "visitor-form",
      "authorization-dates-form",
      "user-form",
      "access-form",
      "member-form",
      "photo-form",
      "voice-form",
      "lab-text-form",
      "lab-token-form",
    ].includes(form.id)
  )
    return;
  event.preventDefault();
  if (formBusy || !form.reportValidity()) return;
  formBusy = true;
  const values = Object.fromEntries(new FormData(form));
  const button = form.querySelector(
    'button[type="submit"], button:not([type])',
  );
  try {
    await withButton(button, async () => {
      const errorEl = form.querySelector(".form-error");
      if (errorEl) errorEl.textContent = "";
      try {
        if (form.id === "login-form") {
          stopSync();
          await login(values.email.trim(), values.password);
          data = await loadData();
          flow = null;
          go(home());
        }
        if (form.id === "booking-form") {
          const c = bookingContext;
          await book(c.service.id, values.date, values.time, c.reservation?.id);
          closeModal();
          await reload();
          go("bookings?tab=mine");
          toast(
            c.reservation
              ? "Tu experiencia tiene un nuevo horario."
              : "Tu reserva está confirmada. Nos encantará recibirte.",
          );
        }
        if (form.id === "user-form") {
          await updateProfile(form.dataset.id, values);
          closeModal();
          await reload();
          toast("Información actualizada.");
        }
        if (form.id === "visitor-form") {
          const payload = {
            ...values,
            name: values.name.trim(),
            valid_from: `${values.valid_from}:00-05:00`,
            valid_until: `${values.valid_until}:00-05:00`,
          };
          const result = await createVisitor(payload);
          await reload();
          await showQR(result, payload.name);
          toast("Registro creado y credencial temporal generada.");
        }
        if (form.id === "authorization-dates-form") {
          await updateAuthorizationDates(form.dataset.table, form.dataset.id, {
            valid_from: values.valid_from,
            valid_until: values.valid_until,
          });
          closeModal();
          await reload();
          toast("Vigencia actualizada.");
        }
        if (form.id === "lab-token-form") {
          memoryToken.set(values.token);
          await api.labStatus();
          toast("Backend en modo memoria conectado.");
          await refreshRobotMonitor();
        }
        if (form.id === "lab-text-form") {
          form.reset();
          await sendLabText(values.text);
        }
        if (form.id === "member-form") await submitMember(form, values);
        if (form.id === "photo-form") {
          const blob = await photoToJpeg(form.querySelector('[name="photo"]').files[0]);
          const result = await api.uploadPhoto(form.dataset.id, blob);
          closeModal();
          toast(result.enrolled ? "Foto registrada: ya se puede reconocer el rostro." : "Foto guardada, pero el rostro no se pudo registrar.");
        }
        if (form.id === "voice-form") {
          await api.uploadVoice(form.dataset.id, form.querySelector('[name="voice"]').files[0]);
          closeModal();
          toast("Voz registrada para verificación de identidad.");
        }
        if (form.id === "access-form") {
          if (
            sessionState.mode === "demo" ||
            sessionState.profile?.role !== "ADMIN"
          )
            throw new Error(
              "La validación real requiere sesión administrativa real.",
            );
          const token = values.token.trim().replace(/^nclub:v1:/, "");
          form.reset();
          const verified = await api.validate({
            credential_token: token,
            method: "qr",
            simulation: false,
          });
          if (!verified.validation_id)
            throw new Error(
              "El backend no devolvió un identificador de validación.",
            );
          const decision = validateDecision(
            await api.check({
              validation_id: verified.validation_id,
              simulation: false,
            }),
            false,
          );
          flow = {
            ...decision,
            step: 4,
            busy: false,
            identity_confirmed: ["authorized", "pending"].includes(decision.access),
            method: (decision.methods || []).join(" + ") || "Credencial QR · Backend",
            stage: stageFor(decision.access),
            message: messageFor(decision),
            reason: decision.reason || "",
            route: decision.route || null,
          };
          if (
            decision.event_type === "vip_handoff" &&
            decision.access === "authorized"
          ) {
            const context = await api.vipContext(decision.visitor_id);
            flow.message = context.message || flow.message;
            flow.reservation_label = context.reservation_label;
          }
          await reload();
        }
      } catch (err) {
        if (errorEl) {
          errorEl.textContent = readableError(err);
          if (form.id === "booking-form") await updateSlots();
        } else throw err;
      }
    });
  } finally {
    formBusy = false;
  }
});

document.querySelector("#modal").addEventListener("click", (event) => {
  if (event.target.id === "modal") {
    const bounds = event.target.getBoundingClientRect();
    if (
      event.clientX < bounds.left ||
      event.clientX > bounds.right ||
      event.clientY < bounds.top ||
      event.clientY > bounds.bottom
    )
      closeModal();
  }
});
document.addEventListener(
  "error",
  (event) => {
    if (event.target.matches?.("[data-robot-stream]"))
      event.target.dataset.failed = "true";
  },
  true,
);
window.addEventListener("hashchange", () => {
  closeModal();
  render();
});
if (supabase)
  supabase.auth.onAuthStateChange((event, session) => {
    if (
      event === "SIGNED_OUT" &&
      sessionState.mode === "live" &&
      sessionState.profile
    ) {
      sessionState.profile = null;
      data = null;
      stopSync();
      go("login");
    }
  });
const initialPath = routeInfo().path;
const publicPaths = new Set(["", "login", "demo", "memberships", "experiences", "ruta"]);
if (!publicPaths.has(initialPath)) {
  app.innerHTML = `<main id="main" class="page-loading">${icon("loader-circle")}Restaurando tu sesión…</main>`;
  try {
    if (!demoEnabled) sessionStorage.removeItem("nclub-demo-profile");
    await restoreSession();
  } catch (err) {
    toast(readableError(err), "error");
  }
} else if (!demoEnabled) {
  sessionStorage.removeItem("nclub-demo-profile");
}
await render();
