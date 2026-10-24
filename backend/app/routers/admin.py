"""Endpoints de la app web: monitoreo ADMIN, stream privado y contrato de recepción."""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse

from ..deps import Context, ctx, current_person, require_admin, stream_token, verify_stream_token
from ..models import CheckRequest, EventRequest, RouteRequest, ValidateRequest
from ..services.access import TOKEN, Decision, parse_time
from ..services.navigation import RouteError, compute_route

router = APIRouter()
DEVICE_ROBOT = "camara-dispositivo"  # mismo valor que services/device_lab.py
ROBOT = r"^[A-Za-z0-9_-]{1,40}$"


def _recent(c: Context, table: str, limit: int = 20) -> list[dict] | None:
    try:
        return c.repo.recent(table, limit)
    except Exception:
        c.state.degraded[table] = "lectura"
        return None


@router.get("/robot/monitor")
def monitor(admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    robot_ids = sorted(set(c.state.robots) | set(c.state.frames)) or ["robot1"]
    robots = [c.reception.robot_status(r) for r in robot_ids]
    # Se prefiere un robot (real o simulador ROS) a la cámara del dispositivo ADMIN.
    agibot = [r for r in robots if r["connected"] and r["robot_id"] != DEVICE_ROBOT]
    primary = next(iter(agibot), None) or next((r for r in robots if r["connected"]), robots[0])
    rid = primary["robot_id"]
    frame = c.state.frames.get(rid)
    camera_live = bool(frame and time.time() - frame[1] < 10)
    transcripts = list(c.state.transcripts)[:10]
    history = list(c.state.history)[:20]
    # Tras reiniciar el backend, el historial proviene de la base.
    stored_sessions = _recent(c, "sesiones_atencion", 20) if not history else None
    active = [c.reception.public(s) for s in c.state.sessions.values() if s["status"] == "ACTIVA"]
    return {
        "connected": primary["connected"],
        "agibot_connected": bool(agibot),
        "device_camera_active": primary["robot_id"] == DEVICE_ROBOT and primary["connected"],
        "lab_available": c.lab is not None,
        "robot_name": primary["name"],
        "robot_id": rid,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "simulation": c.repo.simulated or primary.get("simulated", False),
        "camera_stream_url": (
            f"{c.settings.public_api_url}/robot/stream/{rid}.mjpeg?token={stream_token(c.settings, rid, admin['id'])}"
            if camera_live else None
        ),
        "camera": {"ok": primary.get("camera_ok", False), "live": camera_live,
                   "last_frame_age_s": round(time.time() - frame[1], 1) if frame else None},
        "microphone": {"ok": primary.get("mic_ok", False), "state": primary.get("mic_state", "desconocido")},
        "last_heard": (
            {"transcript": transcripts[0]["texto"], "language": transcripts[0]["idioma"],
             "robot_name": transcripts[0]["robot_id"], "intent": transcripts[0].get("intencion"),
             "created_at": transcripts[0]["created_at"],
             "audio_url": _signed_evidence(c, transcripts[0].get("evidencia_id"))}
            if transcripts else None
        ),
        "transcripts": transcripts,
        "active_sessions": active,
        "events": history,
        "stored_sessions": stored_sessions,
        "robots": robots,
        "persistence": {"ok": not c.state.degraded, "degraded": dict(c.state.degraded)},
    }


def _signed_evidence(c: Context, evidence_id: str | None) -> str | None:
    if not evidence_id:
        return None
    try:
        row = c.repo.one("evidencias", "id", evidence_id)
        return c.repo.signed_url(row["bucket"], row["ruta"], 120) if row else None
    except Exception:
        return None


@router.get("/admin/evidence/{evidence_id}")
def evidence(evidence_id: str, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    url = _signed_evidence(c, evidence_id)
    if not url:
        raise HTTPException(status_code=404, detail="Evidencia no disponible")
    c.reception.audit(f"admin:{admin['id']}", "ver_evidencia", "evidencias", evidence_id)
    return {"url": url, "expires_in": 120}


@router.get("/admin/sessions")
def sessions(limit: int = Query(20, le=100), admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    stored = _recent(c, "sesiones_atencion", limit)
    return {"sessions": stored if stored is not None else list(c.state.history)[:limit],
            "source": "database" if stored is not None else "memory"}


@router.get("/robot/stream/{robot_id}.mjpeg")
async def stream(robot_id: str = Path(pattern=ROBOT), token: str = Query(max_length=300), c: Context = Depends(ctx)):
    """MJPEG privado: token HMAC corto ligado al ADMIN y al robot."""
    if not verify_stream_token(c.settings, robot_id, token):
        raise HTTPException(status_code=401, detail="Token de stream no válido o vencido")

    async def frames():
        started, last = time.time(), 0.0
        while time.time() - started < c.settings.stream_max_s:
            frame = c.state.frames.get(robot_id)
            if frame and frame[1] != last:
                last = frame[1]
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame[0])).encode() \
                    + b"\r\n\r\n" + frame[0] + b"\r\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# ---------- contrato existente de src/api.js ----------

@router.post("/validate")
def validate(body: ValidateRequest, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    if body.simulation:
        raise HTTPException(status_code=400, detail="La validación real no admite simulation:true")
    token = body.credential_token.strip().removeprefix("nclub:v1:")
    if not TOKEN.fullmatch(token) and not c.settings.allow_static_credentials:
        raise HTTPException(status_code=400, detail="Formato de credencial no válido")
    validation_id = secrets.token_urlsafe(24)
    now = time.time()
    with c.state.lock:
        for key in [k for k, v in c.state.validations.items() if v["expires"] < now]:
            c.state.validations.pop(key)
        c.state.validations[validation_id] = {"credential": token, "method": body.method,
                                               "admin": admin["id"], "expires": now + 120}
    return {"validation_id": validation_id}


def _with_outcome(decision: Decision, outcome: str | None) -> Decision:
    if outcome in ("review", "denied"):
        decision.access = outcome
        decision.event_type = "access_check"
        decision.robot_target = "robot1"
        decision.reason = f"Resultado forzado en simulación: {outcome}"
        decision.instruction = "Solicite asistencia en recepción."
        if outcome == "denied":
            decision.destination = None
    return decision


@router.post("/access/check")
def check(body: CheckRequest, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    engine = c.reception.engine
    if body.simulation:
        if not c.settings.allow_simulation:
            raise HTTPException(status_code=403, detail="Simulación deshabilitada en el servidor")
        if not body.visitor_id:
            raise HTTPException(status_code=400, detail="Falta visitor_id")
        decision = _with_outcome(engine.evaluate(persona_id=body.visitor_id, simulation=True), body.requested_outcome)
        origin = f"admin:{admin['id']}:simulacion"
    else:
        with c.state.lock:
            validation = c.state.validations.pop(body.validation_id or "", None)  # un solo uso
        if not validation or validation["expires"] < time.time() or validation["admin"] != admin["id"]:
            raise HTTPException(status_code=404, detail="Validación inexistente o vencida")
        decision = engine.evaluate(credential=validation["credential"])
        origin = f"admin:{admin['id']}"
    decision = c.reception.persist_decision(decision, origin)
    result = decision.to_api()
    if not result["visitor_id"]:
        raise HTTPException(status_code=404, detail=decision.reason)
    # Contrato de src/api.js: pending_escort se presenta como pending.
    result["route"] = c.reception.route_for(decision)
    return result


@router.get("/vip/context/{visitor_id}")
def vip_context(visitor_id: str, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    persona = c.repo.persona(visitor_id)
    if not persona or persona["categoria"] != "VIP":
        raise HTTPException(status_code=404, detail="Contexto VIP no disponible")
    upcoming = sorted(
        (r for r in c.repo.reservations(visitor_id) if parse_time(r["fecha_fin"]) > datetime.now(timezone.utc)),
        key=lambda r: r["fecha_inicio"],
    )
    if not upcoming:
        return {"visitor_id": visitor_id, "message": "Bienvenida a su experiencia exclusiva.", "reservation_label": None}
    r = upcoming[0]
    hour = parse_time(r["fecha_inicio"]).astimezone().strftime("%H:%M")
    return {"visitor_id": visitor_id,
            "message": f"Bienvenida a su experiencia exclusiva. Tiene {r['actividad'].lower()} a las {hour}.",
            "reservation_label": f"{r['actividad']} · {hour}"}


@router.post("/events")
def events(body: EventRequest, persona: dict = Depends(current_person), c: Context = Depends(ctx)):
    if persona["categoria"] not in ("VIP", "REGULAR", "ADMIN"):
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        c.repo.insert("eventos_acceso", {
            "persona_id": persona["id"], "categoria": persona["categoria"], "tipo_evento": body.event_type,
            "estado_acceso": "PENDIENTE", "destino": None, "robot": "robot1", "simulacion": False,
        })
    except Exception as error:
        raise HTTPException(status_code=503, detail="No se pudo registrar la solicitud") from error
    c.reception._publish("assistance", {"persona_id": persona["id"]})
    return {"accepted": True}


@router.post("/navigation/route")
def route(body: RouteRequest, admin: dict = Depends(require_admin)):
    try:
        return compute_route(body.category, body.destination, escort=body.escort)
    except RouteError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
