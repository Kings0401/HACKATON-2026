"""N Club - Backend FastAPI.

    uvicorn app.main:app --reload            (desde backend/)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import BACKEND_DIR, Settings, settings as default_settings
from .deps import Context
from .repository import Repository
from .routers import admin, public, robot
from .services.reception import MonitorState, ReceptionService

log = logging.getLogger("nclub")


def create_app(settings: Settings | None = None, repo: Repository | None = None) -> FastAPI:
    settings = settings or default_settings
    settings.validate()
    if repo is None:
        if settings.mode == "memory":
            from .memory_repo import MemoryRepository

            repo = MemoryRepository(
                faces_dir=BACKEND_DIR.parent / "vision" / "dataset" / "registro",
                admin_token=settings.memory_admin_token,
            )
            log.warning("MODO MEMORIA: datos ficticios, decisiones simulation=true. Token ADMIN: %s",
                        settings.memory_admin_token)
        else:
            from .repository import SupabaseRepository

            repo = SupabaseRepository(settings)
    app = FastAPI(
        title="N Club - Backend",
        description="Identificación, control de acceso, recepción robótica y navegación interior",
        version="2.0.0",
    )
    state = MonitorState()
    app.state.ctx = Context(settings, repo, state, ReceptionService(repo, settings, state))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(public.router)
    app.include_router(robot.router)
    app.include_router(admin.router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str):
    # Creación diferida: importar create_app en pruebas no exige backend/.env.
    global _app
    if name == "app":
        if _app is None:
            logging.basicConfig(level=logging.INFO)
            _app = create_app()
        return _app
    raise AttributeError(name)
