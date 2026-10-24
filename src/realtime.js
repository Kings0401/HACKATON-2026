import { supabase } from "./config.js";
import { sessionState } from "./data.js";

export function subscribe(onChange, onStatus) {
  if (sessionState.mode === "demo") {
    const handler = () => onChange();
    window.addEventListener("storage", handler);
    onStatus("demo");
    return () => window.removeEventListener("storage", handler);
  }
  if (!supabase || !sessionState.profile) return () => {};
  const p = sessionState.profile,
    admin = p.role === "ADMIN";
  let stopped = false;
  let channel = supabase.channel(`nclub-${p.id}`);
  for (const table of [
    "reservas",
    "eventos_acceso",
    "personas",
    "membresias",
    "servicios",
    ...(admin ? ["invitaciones", "permisos_laborales"] : []),
  ]) {
    const column = {
      reservas: "persona_id",
      eventos_acceso: "persona_id",
      personas: "id",
      membresias: "persona_id",
    }[table];
    channel = channel.on(
      "postgres_changes",
      {
        event: "*",
        schema: "public",
        table,
        ...(!admin && column ? { filter: `${column}=eq.${p.id}` } : {}),
      },
      () => onChange(),
    );
  }
  channel.subscribe((status) => {
    if (!stopped) onStatus(status === "SUBSCRIBED" ? "live" : "polling");
  });
  // Also reconciles deletions and missed notifications, always behind RLS.
  const timer = setInterval(() => {
    if (!document.hidden) onChange();
  }, 8000);
  return () => {
    stopped = true;
    clearInterval(timer);
    supabase.removeChannel(channel);
  };
}
