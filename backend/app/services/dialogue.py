"""Comprensión mínima de la voz transcrita (español) para orientar el flujo.

La voz NUNCA confirma identidad ni categoría: solo sugiere qué credencial
pedir y permite responder preguntas frecuentes.
"""

from __future__ import annotations

import re
import unicodedata

INTENTS = [
    ("PROVEEDOR", ("proveedor", "entrega", "mantenimiento", "orden de trabajo", "vengo a reparar", "tecnico", "contratista")),
    ("INVITADO", ("invitado", "invitada", "invitacion", "me invito", "me invitaron", "vengo con", "anfitrion")),
    ("PERSONAL", ("trabajo aqui", "turno", "soy empleado", "soy empleada", "personal", "carne")),
    ("RESERVA", ("reserva", "reserve", "tengo hora", "cancha", "tee time", "partido")),
    ("VIP", ("vip", "lounge", "socio black", "membresia black")),
    ("MIEMBRO", ("soy socio", "soy socia", "soy miembro", "membresia")),
    ("AYUDA", ("ayuda", "recepcionista", "hablar con alguien", "persona humana", "no entiendo")),
    ("SALUDO", ("hola", "buenos dias", "buenas tardes", "buenas noches")),
]

PROMPTS = {
    "PROVEEDOR": ("TRABAJADOR_EXTERNO", "Con gusto. Por favor, muestre el código QR de su orden de servicio."),
    "INVITADO": ("INVITADO", "¡Bienvenidos a N Club! Por favor, muéstrame tu código QR de invitación."),
    "PERSONAL": ("PERSONAL_INTERNO", "Por favor, acerque su carné de personal a la cámara."),
    # Los socios se identifican por rostro (y voz o documento), no con credencial.
    "RESERVA": ("REGULAR", "Con gusto. Para atenderle como socio, mire a mi cámara un momento, por favor."),
    "VIP": ("VIP", "Será un placer atenderle. Mire a mi cámara un momento para reconocerle, por favor."),
    "MIEMBRO": ("REGULAR", "Con gusto. Mire a mi cámara un momento para reconocerle, por favor."),
    "AYUDA": (None, "Enseguida le atiende un miembro de recepción."),
    "SALUDO": (None, "Le damos la bienvenida a N Club. ¿Es socio, invitado, personal o proveedor?"),
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def understand(text: str) -> dict:
    clean = normalize(text)
    for intent, keywords in INTENTS:
        if any(k in clean for k in keywords):
            hint, reply = PROMPTS[intent]
            return {"intent": intent, "category_hint": hint, "reply": reply, "handoff": intent == "AYUDA"}
    return {
        "intent": "DESCONOCIDO",
        "category_hint": None,
        "reply": "Disculpe, ¿podría repetirlo? También puede mostrar su credencial.",
        "handoff": False,
    }
