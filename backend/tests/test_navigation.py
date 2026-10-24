import json
from pathlib import Path

import pytest

from app.services.navigation import ClubMap, RouteError, compute_route, load_map

MAP = Path(__file__).resolve().parents[2] / "shared" / "club-map.json"


@pytest.fixture
def club():
    return load_map(MAP)


def test_map_is_marked_simulated_and_consistent(club):
    assert club.data["simulated"] is True
    graph = club.neighbours()
    # Todo nodo es alcanzable desde recepción (grafo conexo).
    seen, stack = set(), [club.data["start"]]
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(graph[node])
    assert seen == set(club.nodes)


@pytest.mark.parametrize("category,destination,node", [
    ("VIP", "VIP Lounge", "lounge_vip"),
    ("REGULAR", "Campo de golf", "cancha_1"),
    ("INVITADO", "Restaurante principal", "restaurante"),
    ("PERSONAL_INTERNO", "Cocina", "cocina"),
    ("TRABAJADOR_EXTERNO", "Zona técnica", "zona_tecnica"),
])
def test_every_category_reaches_its_destination(club, category, destination, node):
    route = compute_route(category, destination, club_map=club)
    assert route["path"][0] == "recepcion" and route["path"][-1] == node
    allowed = club.allowed_zones(category)
    assert all(club.nodes[n]["zone"] in allowed for n in route["path"])
    assert route["steps"][0]["action"] == "start" and route["steps"][-1]["action"] == "arrive"
    assert route["distance_m"] > 0 and route["minutes"] >= 1


@pytest.mark.parametrize("category,destination", [
    ("REGULAR", "VIP Lounge"),
    ("INVITADO", "Cocina"),
    ("INVITADO", "Campo de golf"),
    ("TRABAJADOR_EXTERNO", "Restaurante principal"),
    ("PERSONAL_INTERNO", "VIP Lounge"),
])
def test_restricted_areas_are_refused(club, category, destination):
    with pytest.raises(RouteError):
        compute_route(category, destination, club_map=club)


def test_staff_kitchen_route_avoids_social_areas(club):
    path = compute_route("PERSONAL_INTERNO", "Cocina", club_map=club)["path"]
    assert path == ["recepcion", "corredor_personal", "cocina"]


def test_turn_instructions(club):
    steps = compute_route("INVITADO", "Restaurante principal", club_map=club)["steps"]
    assert [s["action"] for s in steps] == ["start", "straight", "right", "arrive"]
    assert steps[2]["text"].endswith("Gire a la derecha.")


def test_unknown_destination(club):
    with pytest.raises(RouteError):
        compute_route("VIP", "Helipuerto", club_map=club)


def test_disconnected_edits_are_detected(tmp_path):
    data = json.loads(MAP.read_text(encoding="utf-8"))
    data["edges"] = [e for e in data["edges"] if "paso_servicio" not in e]
    club = ClubMap(data)
    with pytest.raises(RouteError):
        compute_route("TRABAJADOR_EXTERNO", "Zona técnica", club_map=club)
