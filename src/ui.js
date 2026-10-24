import {
  createIcons,
  ArrowDownRight,
  MessageCircle,
  Info,
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  Menu,
  X,
  Flag,
  CalendarDays,
  CalendarCheck,
  QrCode,
  LayoutDashboard,
  Users,
  LogOut,
  ChevronRight,
  ChevronLeft,
  Crown,
  Bell,
  Check,
  CheckCheck,
  CheckCircle2,
  Circle,
  Clock3,
  MapPin,
  Utensils,
  Sparkles,
  ShieldCheck,
  Bot,
  Activity,
  SlidersHorizontal,
  BriefcaseBusiness,
  Plus,
  Search,
  RefreshCw,
  LoaderCircle,
  Download,
  LockKeyhole,
  Mail,
  Eye,
  AlertCircle,
  CircleHelp,
  Sun,
  Leaf,
  HeartHandshake,
  Ticket,
  Building2,
  Send,
  UserRound,
  History,
  ExternalLink,
  Coffee,
  Pencil,
  Trash2,
  Wifi,
  ScanLine,
  Shield,
  Gem,
  Camera,
  AudioLines,
  Mic,
  ScanEye,
  Navigation,
  Route,
  Smartphone,
  Footprints,
  CornerUpLeft,
  CornerUpRight,
  MoveUp,
  Undo2,
  UserCheck,
  WifiOff,
  Radio,
  Hourglass,
  MapPinned,
} from "lucide";
import QRCode from "qrcode";
import { escape, roles } from "./lib.js";

const iconSet = {
  ArrowDownRight,
  MessageCircle,
  Info,
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  Menu,
  X,
  Flag,
  CalendarDays,
  CalendarCheck,
  QrCode,
  LayoutDashboard,
  Users,
  LogOut,
  ChevronRight,
  ChevronLeft,
  Crown,
  Bell,
  Check,
  CheckCheck,
  CheckCircle2,
  Circle,
  Clock3,
  MapPin,
  Utensils,
  Sparkles,
  ShieldCheck,
  Bot,
  Activity,
  SlidersHorizontal,
  BriefcaseBusiness,
  Plus,
  Search,
  RefreshCw,
  LoaderCircle,
  Download,
  LockKeyhole,
  Mail,
  Eye,
  AlertCircle,
  CircleHelp,
  Sun,
  Leaf,
  HeartHandshake,
  Ticket,
  Building2,
  Send,
  UserRound,
  History,
  ExternalLink,
  Coffee,
  Pencil,
  Trash2,
  Wifi,
  ScanLine,
  Shield,
  Gem,
  Camera,
  AudioLines,
  Mic,
  ScanEye,
  Navigation,
  Route,
  Smartphone,
  Footprints,
  CornerUpLeft,
  CornerUpRight,
  MoveUp,
  Undo2,
  UserCheck,
  WifiOff,
  Radio,
  Hourglass,
  MapPinned,
};
export const icon = (name, cls = "") =>
  `<i data-lucide="${name}" class="${cls}" aria-hidden="true"></i>`;
export const brand = (light = false) =>
  `<a class="brand ${light ? "brand-light" : ""}" href="#/" aria-label="N Club World, inicio"><span class="brand-mark">N<span>✦</span></span><span>N CLUB WORLD<small>EXTRAORDINARY BY NATURE</small></span></a>`;
export const badge = (role) =>
  `<span class="badge role-${escape(role?.toLowerCase())}">${role === "VIP" ? icon("crown") : ""}${escape(roles[role] || role)}</span>`;
export const status = (value) => {
  const labels = {
    active: "Activa",
    inactive: "Inactiva",
    suspended: "Suspendida",
    confirmed: "Confirmada",
    cancelled: "Cancelada",
    authorized: "Autorizado",
    denied: "Denegado",
    review: "Revisión requerida",
    pending: "Pendiente",
    revoked: "Revocada",
    expired: "Vencida",
  };
  return /* HTML */ `<span class="status status-${escape(value)}"
    ><span></span>${escape(labels[value] || value)}</span
  >`;
};
export function hydrate() {
  createIcons({ icons: iconSet, attrs: { "stroke-width": 1.65 } });
}
export function toast(message, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", type === "error" ? "alert" : "status");
  el.innerHTML = `${icon(type === "error" ? "alert-circle" : "check-circle-2")}<span>${escape(message)}</span>`;
  document.querySelector("#toasts").append(el);
  hydrate();
  setTimeout(() => el.remove(), 5500);
}
export function modal(title, content, wide = false) {
  const el = document.querySelector("#modal");
  el.className = wide ? "modal-wide" : "";
  el.setAttribute("aria-labelledby", "modal-title");
  document.querySelector("#modal-content").innerHTML =
    `<div class="modal-heading"><div><span class="eyebrow">N Club</span><h2 id="modal-title">${escape(title)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Cerrar">${icon("x")}</button></div>${content}`;
  if (!el.open) el.showModal();
  hydrate();
}
export const closeModal = () => document.querySelector("#modal").close();
export async function drawQR(token, id = "credential-qr") {
  const canvas = document.getElementById(id);
  if (canvas)
    await QRCode.toCanvas(canvas, `nclub:v1:${token}`, {
      width: 260,
      margin: 2,
      errorCorrectionLevel: "M",
      color: { dark: "#102c24", light: "#ffffff" },
    });
}
export async function drawLinkQR(url, id) {
  const canvas = document.getElementById(id);
  if (canvas)
    await QRCode.toCanvas(canvas, url, {
      width: 220,
      margin: 2,
      errorCorrectionLevel: "M",
      color: { dark: "#0b1f19", light: "#ffffff" },
    });
}
export function empty(title, text, action = "") {
  return /* HTML */ `<div class="empty">
    ${icon("leaf")}
    <h3>${escape(title)}</h3>
    <p>${escape(text)}</p>
    ${action}
  </div>`;
}
export function membershipCard(p, compact = false) {
  return /* HTML */ `<div
    class="membership-card ${p.role === "VIP" ? "black-card" : "silver-card"} ${compact ? "compact" : ""}"
  >
    <div class="card-top">
      <span class="card-wordmark">N CLUB WORLD</span
      >${icon(p.role === "VIP" ? "crown" : "shield-check")}
    </div>
    <div class="card-rings" aria-hidden="true"></div>
    <div class="card-type">
      ${p.role === "VIP" ? "BLACK VIP" : "SIGNATURE"}<span>MEMBRESÍA</span>
    </div>
    <div class="card-bottom">
      <div>
        <span class="card-name">${escape(p.full_name)}</span
        ><small>${escape(p.public_id || p.id.slice(0, 8))}</small>
      </div>
      <span class="card-valid"
        >${p.membership_status === "active" ? "MIEMBRO ACTIVO" : "MEMBRESÍA INACTIVA"}</span
      >
    </div>
  </div>`;
}
