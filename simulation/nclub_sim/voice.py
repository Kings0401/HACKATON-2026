"""Voz simulada para la verificación de locutor del backend.

La escena no tiene audio real ni voces grabadas de las personas demo. Cada
persona recibe una «huella» sintética (armónicos con su propio tono y timbre):
una muestra queda como voz registrada en el backend en memoria y, cuando el
visitante habla, el robot envía otra toma distinta de la misma huella. En lugar
del modelo ECAPA se compara el espectro de ambas tomas. El HUD lo rotula
como voz simulada.
"""

from __future__ import annotations

import io
import wave
import zlib

import numpy as np

RATE = 16000
MODEL = "simulado (huella espectral, sin audio real)"


def _profile(persona_id: str) -> tuple[float, np.ndarray]:
    rng = np.random.default_rng(zlib.crc32(persona_id.encode()))
    f0 = float(rng.uniform(95, 240))  # tono fundamental propio
    return f0, rng.uniform(0.15, 1.0, 12)  # peso de cada armónico (timbre)


def utterance_pcm(persona_id: str, take: int, seconds: float = 2.6) -> bytes:
    """Una toma de voz PCM 16 kHz mono de la persona; cada take cambia el ruido."""
    f0, timbre = _profile(persona_id)
    rng = np.random.default_rng(zlib.crc32(f"{persona_id}:{take}".encode()))
    t = np.arange(int(RATE * seconds)) / RATE
    pitch = f0 * (1 + 0.03 * np.sin(2 * np.pi * rng.uniform(2, 4) * t))  # entonación
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    signal = sum(w * np.sin((k + 1) * phase) for k, w in enumerate(timbre))
    syllables = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * rng.uniform(3, 5) * t))
    signal = signal * syllables + rng.normal(0, 0.35, t.size)
    return (signal / np.max(np.abs(signal)) * 9000).astype("<i2").tobytes()


def to_wav(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return out.getvalue()


def _spectrum(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32)
    frames = samples[: len(samples) // 512 * 512].reshape(-1, 512) * np.hanning(512)
    spec = np.log1p(np.abs(np.fft.rfft(frames, axis=1)).mean(axis=0))
    spec -= spec.mean()
    return spec / (np.linalg.norm(spec) or 1.0)


def verify(reference_wav: bytes, spoken_wav: bytes, threshold: float = 0.25) -> dict:
    """Mismo contrato que app.services.speaker_id.verify."""
    similarity = float(np.dot(_spectrum(reference_wav), _spectrum(spoken_wav)))
    threshold = max(threshold, 0.8)  # la huella sintética necesita un umbral más alto
    return {"similarity": similarity, "matched": similarity >= threshold, "threshold": threshold, "model": MODEL}


def verify_many(reference_wavs: list[bytes], spoken_wav: bytes, threshold: float = 0.25) -> dict:
    """Mismo contrato que app.services.speaker_id.verify_many (mayoría de muestras)."""
    results = [verify(reference, spoken_wav, threshold) for reference in reference_wavs]
    matches = sum(r["matched"] for r in results)
    required = len(results) // 2 + 1
    return {"similarity": float(np.median([r["similarity"] for r in results])), "matched": matches >= required,
            "matches": matches, "samples": len(results), "required": required,
            "scores": [r["similarity"] for r in results], "threshold": results[0]["threshold"], "model": MODEL}


def install(repo, persona_ids) -> None:
    """Registra la voz de cada persona y usa el verificador simulado en el backend."""
    from app.services import speaker_id

    speaker_id.verify, speaker_id.verify_many = verify, verify_many
    for pid in persona_ids:
        repo.upload_voice(pid, "enrollment.wav", to_wav(utterance_pcm(pid, take=0)), "audio/wav")
