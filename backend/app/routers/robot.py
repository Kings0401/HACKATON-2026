"""Endpoints del robot (autenticados con X-Robot-Key)."""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from fastapi.responses import Response

from ..deps import Context, ctx, verify_robot
from ..models import CredentialObservation, FaceObservation, Heartbeat, SessionStart, SolicitudAcceso, Utterance
from ..repository import StorageNotFound

router = APIRouter(dependencies=[Depends(verify_robot)])

PERSONA = r"^[A-Za-z0-9_-]{1,50}$"
MAX_FRAME = 600_000


def _session(c: Context, session_id: str) -> dict:
    session = c.reception.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión inexistente")
    if session["status"] != "ACTIVA":
        raise HTTPException(status_code=409, detail="La sesión ya terminó")
    return session


# ---------- fotografías de registro (Storage privado) ----------

@router.get("/rostros")
def listar_personas(c: Context = Depends(ctx)):
    try:
        return {"personas": c.repo.face_folders()}
    except Exception as error:
        raise HTTPException(status_code=502, detail="No se pudo consultar Storage") from error


@router.get("/rostros/{persona_id}")
def obtener_rostros(persona_id: str = Path(pattern=PERSONA), c: Context = Depends(ctx)):
    try:
        fotografias = c.repo.face_files(persona_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail="No se pudieron consultar las fotografías") from error
    return {"persona_id": persona_id, "total_fotografias": len(fotografias), "fotografias": fotografias}


@router.get("/rostros/{persona_id}/{nombre_archivo}")
def descargar_rostro(persona_id: str = Path(pattern=PERSONA), nombre_archivo: str = Path(max_length=200),
                     c: Context = Depends(ctx)):
    # Antes se exigía ^[A-Za-z0-9_.-]+$ y "WhatsApp Image … (1).jpeg" fallaba;
    # además todo error de Storage se devolvía como 404. Ahora el nombre debe
    # existir en el listado real del bucket (sin rutas ni caracteres de control).
    if "/" in nombre_archivo or "\\" in nombre_archivo or nombre_archivo.startswith(".") \
            or re.search(r"[\x00-\x1f]", nombre_archivo) \
            or not nombre_archivo.lower().endswith((".jpg", ".jpeg", ".png")):
        raise HTTPException(status_code=400, detail="Nombre de fotografía no válido")
    try:
        if nombre_archivo not in c.repo.face_files(persona_id):
            raise HTTPException(status_code=404, detail="Fotografía no encontrada")
        imagen = c.repo.download_face(persona_id, nombre_archivo)
    except HTTPException:
        raise
    except StorageNotFound as error:
        raise HTTPException(status_code=404, detail="Fotografía no encontrada") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Storage no respondió; reintente") from error
    media = "image/png" if nombre_archivo.lower().endswith(".png") else "image/jpeg"
    return Response(content=imagen, media_type=media, headers={"Cache-Control": "no-store"})


@router.get("/robot/gallery")
def gallery_manifest(c: Context = Depends(ctx)):
    """El robot consulta esto cada pocos segundos: si cambia la versión, sincroniza."""
    try:
        return c.reception.gallery_manifest()
    except Exception as error:
        raise HTTPException(status_code=502, detail="No se pudo consultar Storage") from error


# ---------- contrato original ----------

@router.post("/resolve-access")
def resolver_acceso(solicitud: SolicitudAcceso, c: Context = Depends(ctx)):
    try:
        decision = c.reception.engine.evaluate(credential=solicitud.credential_code, face_group=solicitud.face_group)
        decision = c.reception.persist_decision(decision, "robot:resolve-access")
    except Exception as error:
        raise HTTPException(status_code=503, detail="No se pudo completar la validación de acceso.") from error
    access = {"pending_escort": "pending_escort", "review": "manual_review"}.get(decision.access, decision.access)
    return {
        "role": decision.category,
        "access": access,
        "destination": decision.destination,
        "instruction": decision.instruction,
        "simulation": decision.simulation,
    }


# ---------- estado y stream ----------

@router.post("/robot/{robot_id}/heartbeat")
def heartbeat(body: Heartbeat, robot_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,40}$"), c: Context = Depends(ctx)):
    return c.reception.heartbeat(robot_id, body.model_dump())


@router.put("/robot/{robot_id}/frame")
async def push_frame(request: Request, robot_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,40}$"),
                     c: Context = Depends(ctx)):
    """Último fotograma JPEG para el stream ADMIN. Solo en memoria, nunca en la base."""
    content = await request.body()
    if not content.startswith(b"\xff\xd8") or len(content) > MAX_FRAME:
        raise HTTPException(status_code=400, detail="Se espera un JPEG de hasta 600 KB")
    with c.state.lock:
        c.state.frames[robot_id] = (content, time.time())
    return {"ok": True}


# ---------- sesiones de atención ----------

@router.post("/robot/sessions")
def start_session(body: SessionStart, c: Context = Depends(ctx)):
    return c.reception.start(body.robot_id, body.simulated)


@router.post("/robot/sessions/{session_id}/faces")
def add_face(session_id: str, body: FaceObservation, c: Context = Depends(ctx)):
    return c.reception.add_face(_session(c, session_id), body.model_dump())


@router.post("/robot/sessions/{session_id}/credentials")
def add_credential(session_id: str, body: CredentialObservation, c: Context = Depends(ctx)):
    return c.reception.add_credential(_session(c, session_id), body.payload, body.kind)


@router.post("/robot/sessions/{session_id}/utterances")
def add_utterance(session_id: str, body: Utterance, c: Context = Depends(ctx)):
    try:
        return c.reception.add_utterance(
            _session(c, session_id), body.text, body.language, body.confidence, body.engine,
            body.started_at, body.ended_at, body.audio_wav_b64, body.consent,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/robot/sessions/{session_id}/evidence")
async def add_evidence(session_id: str, request: Request, consent: bool = False, c: Context = Depends(ctx)):
    """Fotograma puntual de evidencia (no video). Requiere consentimiento y política."""
    session = _session(c, session_id)
    if not (consent and c.settings.store_evidence):
        return {"stored": False, "reason": "STORE_EVIDENCE desactivado o sin consentimiento"}
    content = await request.body()
    if not content.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="Se espera un JPEG")
    try:
        evidence_id = c.reception.store_evidence(session, content, "image/jpeg", "IMAGEN")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"stored": evidence_id is not None, "evidence_id": evidence_id}


@router.post("/robot/sessions/{session_id}/resolve")
def resolve(session_id: str, c: Context = Depends(ctx)):
    session = _session(c, session_id)
    if session["decision"]:  # idempotente: no repite la decisión ni el registro
        return session["decision"]
    try:
        return c.reception.resolve(session)
    except Exception as error:
        raise HTTPException(status_code=503, detail="No se pudo completar la validación de acceso.") from error


@router.post("/robot/sessions/{session_id}/close")
def close(session_id: str, body: dict = Body(default={}), c: Context = Depends(ctx)):
    if not c.reception.get(session_id):
        raise HTTPException(status_code=404, detail="Sesión inexistente")
    c.reception.close(session_id)
    return {"closed": True}

