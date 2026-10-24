"""Navegación interior: grafo del club, Dijkstra con zonas por categoría.

El mapa vive en shared/club-map.json (editable) y es el mismo que dibuja el
frontend. El mapa entregado es esquemático y SIMULADO.
"""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import settings


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class ClubMap:
    data: dict

    @property
    def nodes(self) -> dict:
        return self.data["nodes"]

    def neighbours(self) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {key: [] for key in self.nodes}
        for a, b in self.data["edges"]:
            graph[a].append(b)
            graph[b].append(a)
        return graph

    def node_for(self, destination: str | None) -> str | None:
        if not destination:
            return None
        if destination in self.nodes:
            return destination
        return self.data["destinations"].get(destination.strip())

    def allowed_zones(self, category: str) -> set[str]:
        return set(self.data["access"].get(category, []))

    def distance(self, a: str, b: str) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        return math.hypot(na["x"] - nb["x"], na["y"] - nb["y"]) * self.data["units"]["scale_m_per_unit"]


@lru_cache(maxsize=4)
def _load(path: str) -> ClubMap:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = data["nodes"]
    for a, b in data["edges"]:
        if a not in nodes or b not in nodes:
            raise ValueError(f"Conexión con nodo inexistente: {a} – {b}")
    for alias, node in data["destinations"].items():
        if node not in nodes:
            raise ValueError(f"Destino {alias} apunta a un nodo inexistente")
    return ClubMap(data)


def load_map(path: str | None = None) -> ClubMap:
    return _load(str(path or settings.club_map_path))


def _turn(prev: dict, here: dict, nxt: dict) -> str:
    # Coordenadas SVG: y crece hacia abajo, por eso cruz > 0 es giro a la derecha.
    v1 = (here["x"] - prev["x"], here["y"] - prev["y"])
    v2 = (nxt["x"] - here["x"], nxt["y"] - here["y"])
    angle = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]))
    if abs(angle) < 30:
        return "straight"
    if abs(angle) > 150:
        return "u_turn"
    return "right" if angle > 0 else "left"


TURN_TEXT = {
    "straight": "Continúe recto",
    "left": "Gire a la izquierda",
    "right": "Gire a la derecha",
    "u_turn": "Dé la vuelta",
}

CATEGORY_NOTES = {
    "VIP": "Ruta preferente por el ala VIP. AGIBOT 02 le atenderá personalmente.",
    "REGULAR": "Ruta por las áreas de socios hacia su actividad.",
    "INVITADO": "Ruta limitada a las áreas de su invitación. Su anfitrión ha sido notificado.",
    "PERSONAL_INTERNO": "Ruta por corredores de personal hacia su zona autorizada.",
    "TRABAJADOR_EXTERNO": "Ruta exclusiva de servicio. No ingrese a áreas sociales.",
}


def compute_route(
    category: str,
    destination: str,
    start: str | None = None,
    escort: bool = False,
    club_map: ClubMap | None = None,
) -> dict:
    """Ruta más corta restringida a las zonas que la categoría puede pisar."""
    club_map = club_map or load_map()
    nodes = club_map.nodes
    start = start or club_map.data["start"]
    target = club_map.node_for(destination)
    if target is None:
        raise RouteError(f"Destino sin ubicación en el mapa: {destination}")
    allowed = club_map.allowed_zones(category)
    if not allowed:
        raise RouteError("Categoría sin zonas autorizadas")
    if nodes[target]["zone"] not in allowed:
        raise RouteError("El destino está fuera de las zonas permitidas para la categoría")
    preferences = club_map.data.get("preferences", {}).get(category, {})
    graph = club_map.neighbours()

    best = {start: 0.0}
    previous: dict[str, str] = {}
    pending = [(0.0, start)]
    while pending:
        cost, node = heapq.heappop(pending)
        if node == target:
            break
        if cost > best[node]:
            continue
        for nxt in graph[node]:
            if nodes[nxt]["zone"] not in allowed:
                continue
            step = club_map.distance(node, nxt) * preferences.get(nodes[nxt]["zone"], 1.0)
            if cost + step < best.get(nxt, math.inf):
                best[nxt] = cost + step
                previous[nxt] = node
                heapq.heappush(pending, (cost + step, nxt))
    if target != start and target not in previous:
        raise RouteError("No existe un recorrido permitido hasta el destino")

    path = [target]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()

    meters = sum(club_map.distance(a, b) for a, b in zip(path, path[1:]))
    steps = [
        {
            "node": start,
            "action": "start",
            "text": f"Inicie en {nodes[start]['label']} ({nodes[start]['landmark']}).",
        }
    ]
    for i in range(1, len(path)):
        here = nodes[path[i]]
        leg = round(club_map.distance(path[i - 1], path[i]))
        if i == len(path) - 1:
            steps.append(
                {
                    "node": path[i],
                    "action": "arrive",
                    "meters": leg,
                    "text": f"Avance {leg} m y llegará a {here['label']}: {here['landmark']}.",
                }
            )
            break
        turn = _turn(nodes[path[i - 1]], here, nodes[path[i + 1]])
        steps.append(
            {
                "node": path[i],
                "action": turn,
                "meters": leg,
                "text": f"Avance {leg} m hasta {here['label']} ({here['landmark']}). {TURN_TEXT[turn]}.",
            }
        )
    escort_point = None
    if escort:
        # El acompañamiento comienza en el primer punto de servicio de la ruta.
        escort_point = next(
            (n for n in path if n == "recepcion_proveedores"),
            path[min(1, len(path) - 1)],
        )
        steps.insert(
            path.index(escort_point) + 1,
            {
                "node": escort_point,
                "action": "wait_escort",
                "text": f"Espere a su acompañante en {nodes[escort_point]['label']} antes de continuar.",
            },
        )
    speed = club_map.data["units"]["walking_speed_m_s"]
    return {
        "map_id": club_map.data["id"],
        "simulated": club_map.data.get("simulated", True),
        "category": category,
        "start": start,
        "destination": target,
        "destination_label": nodes[target]["label"],
        "path": path,
        "points": [[nodes[n]["x"], nodes[n]["y"]] for n in path],
        "distance_m": round(meters),
        "minutes": max(1, round(meters / speed / 60)),
        "steps": steps,
        "escort_point": escort_point,
        "note": CATEGORY_NOTES.get(category, ""),
    }
