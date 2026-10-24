"""Endpoints públicos sin datos sensibles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path

from ..deps import Context, ctx
from ..services.navigation import load_map

router = APIRouter()


@router.get("/")
def inicio():
    return {"message": "Bienvenido al backend de N Club", "status": "online"}


@router.get("/health")
def health(c: Context = Depends(ctx)):
    return {
        "status": "ok",
        "database": "memoria (simulación)" if c.repo.simulated else "supabase",
        "simulation": c.repo.simulated,
    }


@router.get("/robot/status")
def robot_status(c: Context = Depends(ctx)):
    """Conexión de los robots (sin cámara, voz ni personas): visible sin sesión."""
    return c.reception.public_status()


@router.get("/navigation/map")
def club_map():
    """Mapa esquemático (simulado); no contiene personas ni permisos."""
    return load_map().data


@router.get("/navigation/shared/{token}")
def shared_route(token: str = Path(min_length=16, max_length=64), c: Context = Depends(ctx)):
    """Ruta para el celular del visitante. Solo lectura: no concede permisos."""
    shared = c.reception.shared_route(token)
    if not shared:
        raise HTTPException(status_code=404, detail="La ruta venció o no existe. Pida una nueva en recepción.")
    route = {k: v for k, v in shared["route"].items() if k not in ("share_url",)}
    return {"route": route, "expires_at": shared["expires_at"]}
