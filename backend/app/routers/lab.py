"""ADMIN: robot simulado con la cámara del dispositivo, alta de miembros y fotos."""

from __future__ import annotations

import time

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from ..deps import Context, ctx, require_admin
from ..models import MemberRequest, TextRequest
from ..services.members import MemberError, create_member, issue_credential

router = APIRouter(prefix="/admin")
PERSONA = r"^[A-Za-z0-9_-]{1,60}$"
MAX_PHOTO = 6_000_000


def _lab(c: Context):
    if c.lab is None:
        raise HTTPException(status_code=503, detail=c.lab_error or "Reconocimiento facial no disponible")
    return c.lab


def _call(fn, *args):
    from ..services.device_lab import LabUnavailable

    try:
        return fn(*args)
    except LabUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# ---------- robot simulado (cámara del dispositivo) ----------

@router.get("/lab/status")
def lab_status(admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    return {"available": c.lab is not None, "error": c.lab_error,
            "gallery": c.gallery.status() if c.gallery else None}


@router.post("/lab/frame")
async def lab_frame(request: Request, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    content = await request.body()
    if not content.startswith(b"\xff\xd8") or len(content) > 1_500_000:
        raise HTTPException(status_code=400, detail="Se espera un JPEG de hasta 1,5 MB")
    return _call(_lab(c).frame, admin["id"], content)


@router.post("/lab/text")
def lab_text(body: TextRequest, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    return _call(_lab(c).text, admin["id"], body.text)


@router.post("/lab/reset")
def lab_reset(admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    if c.lab:
        c.lab.reset(admin["id"])
    return {"reset": True}


@router.post("/lab/reload")
def lab_reload(admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    if not c.gallery:
        raise HTTPException(status_code=503, detail=c.lab_error or "No disponible")
    _call(c.gallery.reload)
    return c.gallery.status()


# ---------- miembros y fotografías de registro ----------

@router.post("/members")
def new_member(body: MemberRequest, admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    try:
        persona = create_member(
            c.repo, body.nombre, body.categoria, body.vigencia_hasta, body.email,
            body.telefono, body.tipo_documento, body.numero_documento,
        )
        credential = issue_credential(c.repo, c.repo.persona(persona["id"]))
    except MemberError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="No se pudo crear el miembro") from error
    c.reception.audit(f"admin:{admin['id']}", "crear_miembro", "persona", persona["id"],
                      {"categoria": persona["categoria"]})
    return {"persona_id": persona["id"], "nombre": persona["nombre"], "categoria": persona["categoria"],
            "credential": credential, "simulation": c.repo.simulated}


@router.post("/personas/{persona_id}/credential")
def member_credential(persona_id: str = Path(pattern=PERSONA), admin: dict = Depends(require_admin),
                      c: Context = Depends(ctx)):
    persona = c.repo.persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona inexistente")
    try:
        return issue_credential(c.repo, persona)
    except MemberError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/personas/{persona_id}/photos")
async def upload_photo(request: Request, persona_id: str = Path(pattern=PERSONA), consent: bool = Query(False),
                       admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    """Foto de registro facial: requiere consentimiento y exactamente un rostro."""
    if not consent:
        raise HTTPException(status_code=400, detail="Se requiere el consentimiento del titular")
    persona = c.repo.persona(persona_id)
    if not persona or persona["categoria"] == "ADMIN":
        raise HTTPException(status_code=404, detail="Persona inexistente")
    content = await request.body()
    if not content or len(content) > MAX_PHOTO:
        raise HTTPException(status_code=400, detail="Imagen vacía o mayor de 6 MB")
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="El archivo no es una imagen válida")
    if c.gallery is None:
        raise HTTPException(status_code=503, detail=c.lab_error or "Reconocimiento facial no disponible")
    faces = _call(c.gallery.count_faces, image)
    if faces != 1:
        raise HTTPException(status_code=422, detail=f"La foto debe mostrar exactamente un rostro (se detectaron {faces}).")
    # Se recodifica: elimina metadatos EXIF/GPS del archivo original.
    if image.shape[1] > 1280:
        image = cv2.resize(image, (1280, int(image.shape[0] * 1280 / image.shape[1])))
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    name = f"admin-{int(time.time())}.jpg"
    try:
        c.repo.upload_face(persona_id, name, buffer.tobytes(), "image/jpeg")
    except Exception as error:
        raise HTTPException(status_code=502, detail="No se pudo guardar la foto en Storage") from error
    enrolled = _call(c.gallery.add, persona_id, image)
    c.reception.audit(f"admin:{admin['id']}", "subir_foto_registro", "persona", persona_id,
                      {"archivo": name, "consentimiento": True})
    return {"persona_id": persona_id, "stored": True, "file": name, "enrolled": enrolled}

