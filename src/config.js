import { createClient } from "@supabase/supabase-js";

const env = import.meta.env || {};
const url = env.VITE_SUPABASE_URL?.trim();
const key = (
  env.VITE_SUPABASE_PUBLISHABLE_KEY || env.VITE_SUPABASE_ANON_KEY
)?.trim();
export const demoEnabled = env.VITE_ENABLE_DEMO !== "false";
export const backendUrl = (env.VITE_BACKEND_URL || "").replace(/\/$/, "");
let client = null;
let error =
  "Completa las variables de Supabase en .env.local para iniciar sesión real.";
let isSecret = key?.startsWith("sb_secret_");
if (key?.split(".").length === 3) {
  try {
    isSecret ||=
      JSON.parse(atob(key.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))
        .role === "service_role";
  } catch {
    /* A malformed public key is handled by Auth. */
  }
}
if (isSecret)
  error =
    "Se detectó una clave privada. Utiliza únicamente la clave pública publishable/anon y retira la clave privada del frontend.";
else if (url && key) {
  try {
    client = createClient(url, key);
    error = "";
  } catch {
    error =
      "La URL de Supabase no es válida. Revisa .env.local y reinicia Vite.";
  }
}
export const supabase = client;
export const configured = Boolean(client);
export const configurationError = error;
