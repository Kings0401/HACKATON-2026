"""ADMIN: robot simulado con la cámara del dispositivo, alta de miembros y fotos."""

from __future__ import annotations

import time
import io
import wave
import base64
import mimetypes
import logging
from datetime import timedelta

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from ..deps import Context, ctx, require_admin
from ..models import InvitationDates, MemberRequest, TextRequest
from ..services.members import MemberError, create_member, issue_credential

router = APIRouter(prefix="/admin")
log = logging.getLogger(__name__)
PERSONA = r"^[A-Za-z0-9_-]{1,60}$"
MAX_PHOTO = 6_000_000
MAX_VOICE = 8_000_000


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


@router.patch("/invitations/{codigo_qr}")
def update_invitation_dates(body: InvitationDates, codigo_qr: str = Path(min_length=1, max_length=200),
                            admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    """ADMIN-only adjustment of an invitation window; past windows remain editable for access checks."""
    if body.valid_from.tzinfo is None or body.valid_until.tzinfo is None:
        raise HTTPException(status_code=422, detail="Las fechas deben incluir zona horaria de Colombia.")
    if body.valid_until <= body.valid_from:
        raise HTTPException(status_code=422, detail="La fecha final debe ser posterior a la inicial.")
    if body.valid_until - body.valid_from > timedelta(days=7):
        raise HTTPException(status_code=422, detail="La vigencia de una invitación no puede superar 7 días.")
    invitation = c.repo.one("invitaciones", "codigo_qr", codigo_qr)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitación inexistente.")
    if invitation.get("estado") != "ACTIVA":
        raise HTTPException(status_code=409, detail="Solo se pueden editar invitaciones activas.")
    try:
        c.repo.update("invitaciones", "codigo_qr", codigo_qr, {
            "valido_desde": body.valid_from.isoformat(),
            "valido_hasta": body.valid_until.isoformat(),
        })
    except Exception as error:
        log.exception("No se pudo cambiar la vigencia de la invitación %s", codigo_qr)
        raise HTTPException(status_code=503, detail="No se pudo actualizar la invitación.") from error
    c.reception.audit(f"admin:{admin['id']}", "editar_vigencia_invitacion", "invitaciones", codigo_qr,
                      {"valido_desde": body.valid_from.isoformat(), "valido_hasta": body.valid_until.isoformat()})
    return {"codigo_qr": codigo_qr, "valido_desde": body.valid_from.isoformat(),
            "valido_hasta": body.valid_until.isoformat(), "updated": True}


@router.patch("/work-assignments/{codigo_autorizacion}")
def update_external_assignment_dates(body: InvitationDates,
                                     codigo_autorizacion: str = Path(min_length=1, max_length=200),
                                     admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    """ADMIN-only adjustment of an external order or internal staff shift window."""
    if body.valid_from.tzinfo is None or body.valid_until.tzinfo is None:
        raise HTTPException(status_code=422, detail="Las fechas deben incluir zona horaria de Colombia.")
    if body.valid_until <= body.valid_from:
        raise HTTPException(status_code=422, detail="La fecha final debe ser posterior a la inicial.")
    if body.valid_until - body.valid_from > timedelta(days=7):
        raise HTTPException(status_code=422, detail="La vigencia no puede superar 7 días.")
    assignment = c.repo.one("permisos_laborales", "codigo_autorizacion", codigo_autorizacion)
    if not assignment:
        raise HTTPException(status_code=404, detail="Autorización inexistente.")
    assignment_type = assignment.get("tipo")
    if assignment_type not in {"TRABAJADOR_EXTERNO", "PERSONAL_INTERNO"}:
        raise HTTPException(status_code=403, detail="Solo se pueden editar turnos de personal u órdenes externas.")
    if assignment.get("estado") != "ACTIVO":
        raise HTTPException(status_code=409, detail="Solo se pueden editar autorizaciones activas.")
    try:
        c.repo.update("permisos_laborales", "codigo_autorizacion", codigo_autorizacion, {
            "valido_desde": body.valid_from.isoformat(),
            "valido_hasta": body.valid_until.isoformat(),
        })
    except Exception as error:
        log.exception("No se pudo cambiar la vigencia del permiso externo %s", codigo_autorizacion)
        raise HTTPException(status_code=503, detail="No se pudo actualizar la autorización.") from error
    audit_action = "editar_horario_turno" if assignment_type == "PERSONAL_INTERNO" else "editar_vigencia_permiso_externo"
    c.reception.audit(f"admin:{admin['id']}", audit_action, "permisos_laborales",
                      codigo_autorizacion,
                      {"valido_desde": body.valid_from.isoformat(), "valido_hasta": body.valid_until.isoformat()})
    return {"codigo_autorizacion": codigo_autorizacion, "valido_desde": body.valid_from.isoformat(),
            "valido_hasta": body.valid_until.isoformat(), "updated": True}


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
    c.reception.invalidate_gallery()  # el robot la descarga en segundos
    c.reception.audit(f"admin:{admin['id']}", "subir_foto_registro", "persona", persona_id,
                      {"archivo": name, "consentimiento": True})
    return {"persona_id": persona_id, "stored": True, "file": name, "enrolled": enrolled}


@router.get("/personas/{persona_id}/biometrics")
def persona_biometrics(persona_id: str = Path(pattern=PERSONA), admin: dict = Depends(require_admin),
                       c: Context = Depends(ctx)):
    """Signed previews of private enrollment photos and voice samples."""
    if not c.repo.persona(persona_id):
        raise HTTPException(status_code=404, detail="Persona inexistente")

    def preview(bucket: str, name: str, mime: str) -> str | None:
        if c.repo.simulated:
            try:
                content = (c.repo.download_face(persona_id, name) if mime.startswith("image/")
                           else c.repo.download_voice(persona_id, name))
            except Exception:
                return None
            return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
        return c.repo.signed_url(bucket, f"{persona_id}/{name}", 300)

    photos = [{"name": name, "url": preview(c.settings.faces_bucket, name,
                                                mimetypes.guess_type(name)[0] or "image/jpeg")}
              for name in c.repo.face_files(persona_id)]
    voices = [{"name": name, "url": preview(c.settings.voices_bucket, name, "audio/wav"),
               "sample_id": int(name.removeprefix("frase-").removesuffix(".wav"))
               if name.startswith("frase-") and name.endswith(".wav") and name[6:-4].isdigit() else None}
              for name in c.repo.voice_files(persona_id)]
    return {"persona_id": persona_id, "photos": [item for item in photos if item["url"]],
            "voices": [item for item in voices if item["url"]]}


@router.post("/personas/{persona_id}/voice")
async def upload_voice(request: Request, persona_id: str = Path(pattern=PERSONA), consent: bool = Query(False),
                       sample_id: int = Query(1, ge=1, le=3),
                       admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    """Enrollment phrase for Speaker ID. WAV PCM mono, 16 kHz, 16 bits, 3–20 s."""
    if not consent:
        raise HTTPException(status_code=400, detail="Se requiere el consentimiento del titular para registrar su voz")
    persona = c.repo.persona(persona_id)
    if not persona or persona["categoria"] == "ADMIN":
        raise HTTPException(status_code=404, detail="Persona inexistente")
    content = await request.body()
    if not content or len(content) > MAX_VOICE:
        raise HTTPException(status_code=400, detail="Audio vacío o mayor de 8 MB")
    try:
        with wave.open(io.BytesIO(content), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            valid = (wav.getnchannels() == 1 and wav.getframerate() == 16000 and
                     wav.getsampwidth() == 2 and 3 <= duration <= 20)
    except (wave.Error, EOFError, ZeroDivisionError) as error:
        raise HTTPException(status_code=400, detail="Sube una grabación WAV válida") from error
    if not valid:
        raise HTTPException(status_code=422, detail="La muestra debe durar 3–20 s y ser WAV PCM mono de 16 kHz y 16 bits")
    name = f"frase-{sample_id}.wav"
    try:
        c.repo.upload_voice(persona_id, name, content, "audio/wav")
    except Exception as error:
        log.exception("No se pudo guardar muestra de voz para persona %s", persona_id)
        message = str(error).lower()
        if "bucket" in message and ("not found" in message or "does not exist" in message):
            detail = "No existe el bucket privado voces-nclub. Ejecuta supabase/recepcion_robot.sql y reinicia FastAPI."
        elif "unauthorized" in message or "forbidden" in message or "permission" in message:
            detail = "Supabase rechazó la escritura de voz. Revisa SUPABASE_SECRET_KEY y los permisos de Storage del backend."
        else:
            detail = "No se pudo guardar la muestra en Storage privado. Revisa el log de FastAPI para ver el error de Supabase."
        raise HTTPException(status_code=502, detail=detail) from error
    c.reception.audit(f"admin:{admin['id']}", "registrar_voz", "persona", persona_id,
                      {"archivo": name, "muestra": sample_id, "consentimiento": True,
                       "duracion_s": round(duration, 2)})
    return {"persona_id": persona_id, "stored": True, "file": name, "sample_id": sample_id,
            "speaker_model": "ECAPA-TDNN"}


@router.post("/personas/{persona_id}/voice/verify")
async def verify_voice(request: Request, persona_id: str = Path(pattern=PERSONA), consent: bool = Query(False),
                       admin: dict = Depends(require_admin), c: Context = Depends(ctx)):
    """Evaluate a transient test phrase against the person's enrolled voice samples."""
    if not consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento para evaluar la voz")
    persona = c.repo.persona(persona_id)
    if not persona or persona["categoria"] == "ADMIN":
        raise HTTPException(status_code=404, detail="Persona inexistente")
    content = await request.body()
    if not content or len(content) > MAX_VOICE:
        raise HTTPException(status_code=400, detail="Audio vacío o mayor de 8 MB")
    files = c.repo.voice_files(persona_id)
    phrase_files = [name for name in files if name.startswith("frase-") and name.endswith(".wav")]
    phrase_ids = {name[6:-4] for name in phrase_files if name[6:-4].isdigit()}
    if phrase_files:
        references = phrase_files if {"1", "2", "3"}.issubset(phrase_ids) else []
    else:
        references = ["enrollment.wav"] if "enrollment.wav" in files else files[:1]
    if not references:
        raise HTTPException(status_code=409, detail="Registra primero las tres frases de enrolamiento")
    try:
        from ..services.speaker_id import verify_many

        result = verify_many([c.repo.download_voice(persona_id, name) for name in references], content,
                             c.settings.speaker_threshold)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        log.exception("Voice recognition failed for persona %s", persona_id)
        if isinstance(error, ModuleNotFoundError):
            raise HTTPException(status_code=503, detail="Faltan dependencias de voz. Instala backend/requirements.txt y reinicia FastAPI.") from error
        raise HTTPException(status_code=503, detail="El reconocimiento de voz no está disponible") from error
    c.reception.audit(f"admin:{admin['id']}", "probar_reconocimiento_voz", "persona", persona_id,
                      {"coincide": result["matched"], "muestras": result["samples"],
                       "coincidencias": result["matches"], "similitud": result["similarity"]})
    return result

