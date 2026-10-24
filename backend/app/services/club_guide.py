"""Guía del club para la conversación del robot.

Responde preguntas como «¿dónde queda el restaurante?» o «¿cómo llego a la
cancha 2?» con el mapa de shared/club-map.json: distancia, tiempo y primeras
indicaciones, respetando las zonas de cada una de las cinco categorías. Solo
usa datos del mapa (esquemático y SIMULADO); no inventa servicios ni horarios.
"""

from __future__ import annotations

import heapq
import math

from .dialogue import normalize
from .navigation import RouteError, compute_route, load_map

# Formas habituales de nombrar cada espacio (en minúsculas y sin tildes).
ALIASES = {
    "recepcion": ("recepcion principal", "la recepcion", "entrada"),
    "lobby": ("lobby", "fuente"),
    "recepcion_golf": ("recepcion de golf", "carritos", "carro de golf", "tee"),
    "operacion_golf": ("operacion de golf", "taller de carritos"),
    "cancha_1": ("cancha 1", "cancha uno", "hoyo 1", "campo de golf", "campo", "golf"),
    "cancha_2": ("cancha 2", "cancha dos", "hoyo 2", "lago"),
    "cancha_3": ("cancha 3", "cancha tres", "hoyo 3"),
    "cancha_4": ("cancha 4", "cancha cuatro", "hoyo 4"),
    "cancha_5": ("cancha 5", "cancha cinco", "hoyo 5"),
    "recepcion_miembros": ("recepcion de miembros", "recepcion de socios", "socios"),
    "galeria": ("galeria", "trofeos"),
    "restaurante": ("restaurante", "comer", "almorzar", "cenar", "terraza", "mesa"),
    "recepcion_vip": ("recepcion vip",),
    "lounge_vip": ("lounge", "sala vip", "zona vip", "vip lounge"),
    "oficina_admin": ("oficina administrativa", "administracion", "oficina"),
    "cocina": ("cocina",),
    "recepcion_proveedores": ("recepcion de proveedores", "proveedores", "caseta"),
    "entrada_servicio": ("entrada de servicio", "porton de servicio", "carga"),
    "mantenimiento": ("mantenimiento", "bodega"),
    "zona_tecnica": ("zona tecnica", "cuarto electrico", "electrico"),
}
WHERE = ("donde", "como llego", "como voy", "como puedo llegar", "queda", "ubicado", "ubicada",
         "llegar a", "ir a", "ir al", "camino", "direccion", "indicaciones", "cuanto falta", "lejos", "cerca")
LIST = ("que espacios", "que lugares", "que hay", "que tiene el club", "instalaciones", "a donde puedo ir")
CATEGORY_NAME = {
    "VIP": "miembro VIP", "REGULAR": "miembro", "INVITADO": "invitado",
    "PERSONAL_INTERNO": "personal del club", "TRABAJADOR_EXTERNO": "proveedor",
}
# Para personas aún no verificadas se describe el lugar, sin guiar a zonas restringidas.
PUBLIC_ZONES = {"PUBLICA"}


def find_place(clean: str) -> str | None:
    best, best_len = None, 0
    nodes = load_map().nodes
    for node, words in ALIASES.items():
        for word in (*words, normalize(nodes[node]["label"])):
            if word in clean and len(word) > best_len:
                best, best_len = node, len(word)
    return best


def _distance_any(club, start: str, target: str) -> float:
    """Distancia física (sin restricciones de zona) para describir un lugar."""
    graph = club.neighbours()
    best = {start: 0.0}
    pending = [(0.0, start)]
    while pending:
        cost, node = heapq.heappop(pending)
        if node == target:
            return cost
        for nxt in graph[node]:
            step = cost + club.distance(node, nxt)
            if step < best.get(nxt, math.inf):
                best[nxt] = step
                heapq.heappush(pending, (step, nxt))
    return math.inf


def spoken_steps(route: dict, limit: int = 3) -> str:
    """Indicaciones breves para decir en voz alta."""
    club = load_map()
    parts = []
    for step in route["steps"][1:]:
        label = club.nodes[step["node"]]["label"]
        meters = step.get("meters")
        if step["action"] == "arrive":
            parts.append(f"en {meters} metros llegará a {label}")
        elif step["action"] == "wait_escort":
            parts.append(f"espere a su acompañante en {label}")
        else:
            turn = {"left": "gire a la izquierda", "right": "gire a la derecha",
                    "u_turn": "dé la vuelta", "straight": "siga derecho"}[step["action"]]
            parts.append(f"avance {meters} metros hasta {label} y {turn}")
        if len(parts) >= limit and step["action"] != "arrive":
            parts.append("y siga las indicaciones del mapa")
            break
    if not parts:
        return ""
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def describe_places(category: str | None) -> str:
    club = load_map()
    zones = club.allowed_zones(category) if category else PUBLIC_ZONES | {"SOCIOS"}
    names = sorted({
        n["label"] for n in club.nodes.values()
        if n["kind"] == "destination" and n["zone"] in zones and not n["label"].startswith("Cancha")
    })
    has_courts = "CAMPO" in zones
    listing = ", ".join(names) + (", y las cinco canchas del campo de golf" if has_courts else "")
    who = f"Como {CATEGORY_NAME[category]}, puede ir a" if category else "En el club encontrará"
    return f"{who}: {listing}."


def answer(text: str, category: str | None = None) -> dict | None:
    """Respuesta de orientación o None si la frase no trata de lugares.

    category es la categoría CONFIRMADA por credencial; sin ella solo se
    describe el lugar y se pide la credencial antes de guiar.
    """
    clean = normalize(text)
    if any(k in clean for k in LIST):
        return {"intent": "ESPACIOS", "reply": describe_places(category), "route": None}
    place = find_place(clean)
    if not place or not (any(k in clean for k in WHERE) or len(clean.split()) <= 4):
        return None
    club = load_map()
    node = club.nodes[place]
    if category is None:
        meters = _distance_any(club, club.data["start"], place)
        minutes = max(1, round(meters / club.data["units"]["walking_speed_m_s"] / 60))
        reply = (f"{node['label']} está a unos {round(meters)} metros de recepción, cerca de {minutes} "
                 f"minuto{'s' if minutes != 1 else ''} a pie. Para indicarle el camino, primero confirmemos "
                 "su ingreso: muestre su credencial, por favor.")
        return {"intent": "UBICACION", "reply": reply, "route": None}
    try:
        route = compute_route(category, place)
    except RouteError:
        return {"intent": "UBICACION",
                "reply": f"{node['label']} no está incluido en su acceso como {CATEGORY_NAME[category]}. "
                         "Si lo necesita, un miembro de recepción le ayudará.",
                "route": None}
    reply = (f"{node['label']} está a {route['distance_m']} metros, unos {route['minutes']} "
             f"minuto{'s' if route['minutes'] != 1 else ''} caminando. {spoken_steps(route)}")
    return {"intent": "UBICACION", "reply": reply, "route": route}
