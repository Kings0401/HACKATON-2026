// Robot simulado con la cámara y el micrófono de ESTE dispositivo.
// Solo se activa con un clic del ADMIN y cuando no hay un AGIBOT conectado.
// Los fotogramas van al backend, que ejecuta el mismo agente del robot
// (rostro + QR + voz + decisión + ruta); no se guardan ni se graba video.
import { api, memoryToken } from "./api.js";
import { backendUrl } from "./config.js";
import { sessionState } from "./data.js";
import { escape as e, readableError } from "./lib.js";
import { routeCard, shareUrlFor, revealRoutes } from "./navigation.js";
import { icon, hydrate, drawLinkQR, toast } from "./ui.js";

const FRAME_MS = 650;
const Recognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;
let stream = null,
  timer = null,
  busy = false,
  recognizer = null,
  lastSession = null,
  lastDecisionKey = "",
  voiceOn = true;

const decisionNames = {
  AUTORIZADO: "Acceso autorizado",
  DENEGADO: "Acceso denegado",
  REVISION: "Revisión en recepción",
  ACOMPANAMIENTO: "Espera de acompañamiento",
};
const decisionClass = {
  AUTORIZADO: "authorized",
  DENEGADO: "denied",
  REVISION: "review",
  ACOMPANAMIENTO: "pending",
};

export const deviceLabActive = () => Boolean(stream);

export function deviceLabPanel() {
  const demo = sessionState.mode === "demo";
  const needsToken = demo && backendUrl;
  return `<section class="panel device-lab" data-device-lab>
    <div class="monitor-section-heading"><div><span class="eyebrow">Robot simulado en este dispositivo</span><strong>Probar con la cámara del dispositivo</strong></div><span class="demo-tag">Simulación</span></div>
    <p class="device-lab-intro">Si no hay un AGIBOT conectado, este equipo actúa como el robot: su cámara envía fotogramas al backend, que reconoce rostros, lee el QR, decide el acceso según la membresía y traza la ruta. El reconocimiento facial solo saluda: el ingreso siempre exige credencial.</p>
    <p class="notice device-lab-agibot" data-lab-agibot hidden>${icon("bot")} Hay un AGIBOT conectado: el monitor muestra su cámara real.</p>
    ${
      !backendUrl
        ? `<div class="notice">${icon("alert-circle")}<p>Configure <code>VITE_BACKEND_URL</code> y ejecute FastAPI: el reconocimiento se hace en el servidor.</p></div>`
        : needsToken
          ? `<form class="device-lab-token" id="lab-token-form"><label>Token ADMIN del backend en modo memoria<input name="token" type="password" autocomplete="off" placeholder="Lo imprime uvicorn al iniciar" value="${e(memoryToken.get())}" required /></label><button class="button outline">${icon("check")} Usar token</button><small>Solo para pruebas con datos ficticios (NCLUB_BACKEND_MODE=memory). En producción inicie sesión ADMIN real.</small></form>`
          : ""
    }
    <div class="device-lab-grid">
      <div class="device-lab-stage">
        <video data-lab-video playsinline muted></video>
        <canvas data-lab-overlay aria-hidden="true"></canvas>
        <div class="device-lab-idle" data-lab-idle>${icon("camera")}<strong>Cámara apagada</strong><span>Se solicitará permiso al navegador. Puede mostrar un rostro registrado y luego el QR de la credencial.</span></div>
      </div>
      <div class="device-lab-side">
        <div class="device-lab-controls">
          <button class="button primary" data-action="lab-start" ${backendUrl ? "" : "disabled"}>${icon("camera")} Activar cámara</button>
          <button class="button outline" data-action="lab-stop" hidden>${icon("x")} Detener</button>
          <button class="button outline" data-action="lab-mic" ${Recognition ? "" : "disabled title='El navegador no admite reconocimiento de voz'"} hidden>${icon("mic")} Hablar</button>
          <label class="device-lab-voice"><input type="checkbox" data-lab-voice checked /> Voz del robot</label>
        </div>
        <form class="device-lab-say" id="lab-text-form" hidden><input name="text" maxlength="500" autocomplete="off" placeholder="Escriba lo que diría el visitante…" aria-label="Frase del visitante" /><button class="icon-button" aria-label="Enviar frase">${icon("send")}</button></form>
        <div class="device-lab-status" data-lab-status>${icon("scan-eye")} En espera</div>
        <ol class="device-lab-chat" data-lab-chat aria-live="polite"></ol>
      </div>
    </div>
    <div data-lab-decision></div>
  </section>`;
}

function setStatus(html) {
  const el = document.querySelector("[data-lab-status]");
  if (el) {
    el.innerHTML = html;
    hydrate();
  }
}

function addChat(who, text) {
  const chat = document.querySelector("[data-lab-chat]");
  if (!chat || !text) return;
  const li = document.createElement("li");
  li.className = who;
  li.innerHTML = `<strong>${who === "robot" ? "Robot" : "Visitante"}</strong>${e(text)}`;
  chat.prepend(li);
  while (chat.children.length > 8) chat.lastElementChild.remove();
}

function speak(text) {
  if (!voiceOn || !("speechSynthesis" in window) || !text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "es-CO";
  const voice = speechSynthesis
    .getVoices()
    .find((v) => v.lang?.toLowerCase().startsWith("es"));
  if (voice) utterance.voice = voice;
  speechSynthesis.speak(utterance);
}

function drawOverlay(result) {
  const video = document.querySelector("[data-lab-video]");
  const canvas = document.querySelector("[data-lab-overlay]");
  if (!video || !canvas || !result.frame) return;
  canvas.width = result.frame.width;
  canvas.height = result.frame.height;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.lineWidth = Math.max(2, canvas.width / 320);
  ctx.font = `${Math.max(14, canvas.width / 40)}px Manrope, sans-serif`;
  for (const face of result.faces) {
    const [x, y, w, h] = face.box;
    const known = Boolean(face.persona_id);
    ctx.strokeStyle = known ? "#5eead4" : "#fc8181";
    ctx.strokeRect(x, y, w, h);
    const label = `${face.persona_id || "Desconocido"} · ${face.similarity.toFixed(2)}`;
    ctx.fillStyle = "rgba(4,16,19,.75)";
    ctx.fillRect(x, Math.max(0, y - 28), ctx.measureText(label).width + 14, 26);
    ctx.fillStyle = known ? "#5eead4" : "#fc8181";
    ctx.fillText(label, x + 7, Math.max(18, y - 9));
  }
}

async function showDecision(decision) {
  const box = document.querySelector("[data-lab-decision]");
  if (!box) return;
  if (!decision) {
    box.innerHTML = "";
    return;
  }
  const key = `${lastSession}:${decision.decision}`;
  if (key === lastDecisionKey) return;
  lastDecisionKey = key;
  box.innerHTML = `<div class="device-lab-result status-card-${decisionClass[decision.decision] || "pending"}">
      <span class="status status-${decisionClass[decision.decision] || "pending"}"><span></span>${e(decisionNames[decision.decision] || decision.decision)}</span>
      <h3>${e(decision.visitor_name || "Visitante no identificado")}</h3>
      <p>${e(decision.reason || "")}</p>
      <ul class="check-list">${(decision.checks || []).map((c) => `<li class="${c.ok ? "ok" : "fail"}">${icon(c.ok ? "check-circle-2" : "alert-circle")}<strong>${e(c.name)}</strong><span>${e(c.detail)}</span></li>`).join("")}</ul>
    </div>
    ${decision.route?.steps ? routeCard(decision.route, { qrId: "lab-route-qr", title: "Ruta del visitante · simulación" }) : ""}`;
  hydrate();
  if (decision.route?.steps)
    await drawLinkQR(shareUrlFor(decision.route), "lab-route-qr");
  revealRoutes(box);
}

async function handle(result) {
  if (result.session_id !== lastSession) {
    lastSession = result.session_id;
    if (!result.decision) showDecision(null);
  }
  for (const line of result.speech || []) {
    addChat("robot", line);
    speak(line);
  }
  drawOverlay(result);
  const known = result.faces?.find((f) => f.persona_id);
  setStatus(
    result.decision
      ? `${icon("shield-check")} Decisión emitida · ${e(decisionNames[result.decision.decision] || "")}`
      : result.qr?.length
        ? `${icon("qr-code")} QR leído (${e(result.qr[0].kind)})`
        : known
          ? `${icon("user-check")} Rostro reconocido: ${e(known.persona_id)} · muestre su credencial`
          : result.faces?.length
            ? `${icon("scan-eye")} Rostro no registrado o similitud insuficiente`
            : `${icon("scan-eye")} Buscando rostro o QR…`,
  );
  if (result.decision) await showDecision(result.decision);
}

async function captureFrame() {
  if (busy || !stream) return;
  const video = document.querySelector("[data-lab-video]");
  if (!video?.videoWidth) return;
  busy = true;
  try {
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 960 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.8));
    await handle(await api.labFrame(blob));
  } catch (err) {
    setStatus(`${icon("alert-circle")} ${e(readableError(err))}`);
  } finally {
    busy = false;
  }
}

export async function startDeviceLab() {
  if (stream) return;
  if (!navigator.mediaDevices?.getUserMedia)
    throw new Error(
      "Este navegador no permite usar la cámara (se requiere HTTPS o localhost).",
    );
  await api.labStatus(); // valida sesión ADMIN y disponibilidad del reconocimiento
  stream = await navigator.mediaDevices.getUserMedia({
    video: {
      facingMode: "user",
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
    audio: false,
  });
  const video = document.querySelector("[data-lab-video]");
  video.srcObject = stream;
  await video.play();
  document.querySelector("[data-lab-idle]").hidden = true;
  document.querySelector('[data-action="lab-start"]').hidden = true;
  document.querySelector('[data-action="lab-stop"]').hidden = false;
  document.querySelector('[data-action="lab-mic"]').hidden = false;
  document.querySelector("#lab-text-form").hidden = false;
  timer = setInterval(captureFrame, FRAME_MS);
  setStatus(`${icon("scan-eye")} Buscando rostro o QR…`);
}

export function stopDeviceLab() {
  clearInterval(timer);
  timer = null;
  recognizer?.stop();
  recognizer = null;
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  lastSession = null;
  lastDecisionKey = "";
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  api.labReset().catch(() => {
    /* El backend cierra la sesión por inactividad si no responde. */
  });
  const idle = document.querySelector("[data-lab-idle]");
  if (idle) {
    idle.hidden = false;
    document.querySelector('[data-action="lab-start"]').hidden = false;
    document.querySelector('[data-action="lab-stop"]').hidden = true;
    document.querySelector('[data-action="lab-mic"]').hidden = true;
    document.querySelector("#lab-text-form").hidden = true;
    const canvas = document.querySelector("[data-lab-overlay]");
    canvas?.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    setStatus(`${icon("scan-eye")} En espera`);
  }
}

export async function sendLabText(text) {
  if (!text.trim()) return;
  addChat("visitor", text);
  const result = await api.labText(text);
  await handle(result);
}

export function toggleLabMic(button) {
  if (!Recognition) return;
  if (recognizer) {
    recognizer.stop();
    return;
  }
  recognizer = new Recognition();
  recognizer.lang = "es-CO";
  recognizer.interimResults = false;
  recognizer.continuous = false;
  button.classList.add("is-listening");
  recognizer.onresult = (event) => {
    const text = event.results[0]?.[0]?.transcript || "";
    sendLabText(text).catch((err) => toast(readableError(err), "error"));
  };
  recognizer.onerror = (event) => toast(`Micrófono: ${event.error}`, "error");
  recognizer.onend = () => {
    recognizer = null;
    button.classList.remove("is-listening");
  };
  recognizer.start();
}

export function setLabVoice(on) {
  voiceOn = on;
  if (!on && "speechSynthesis" in window) speechSynthesis.cancel();
}

export function markAgibot(connected) {
  const note = document.querySelector("[data-lab-agibot]");
  if (note) note.hidden = !connected;
  if (connected && stream) {
    stopDeviceLab();
    toast("Se conectó un AGIBOT: se detuvo la cámara del dispositivo.");
  }
}

// Reduce y recodifica una foto (elimina EXIF) antes de subirla.
export async function photoToJpeg(file, max = 1280) {
  if (!file?.type?.startsWith("image/"))
    throw new Error("Seleccione una imagen.");
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    // Formatos que el navegador no decodifica (p. ej. HEIC): el backend lo
    // decodifica y recodifica sin metadatos.
    if (file.size > 6_000_000) throw new Error("La imagen supera 6 MB.");
    return file;
  }
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
}
