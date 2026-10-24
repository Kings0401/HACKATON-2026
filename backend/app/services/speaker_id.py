"""Verificación de locutor con ECAPA-TDNN sobre WAV PCM 16 kHz mono."""

from __future__ import annotations

import io
import threading
import wave

import numpy as np

MODEL = "speechbrain/spkrec-ecapa-voxceleb"
_lock = threading.RLock()
_model = None


def _waveform(content: bytes):
    import torch

    try:
        with wave.open(io.BytesIO(content), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getframerate() != 16000 or wav.getsampwidth() != 2:
                raise ValueError("El audio debe ser WAV PCM mono de 16 kHz y 16 bits")
            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    except (wave.Error, EOFError) as error:
        raise ValueError("El audio no es un WAV válido") from error
    seconds = len(samples) / 16000
    if not 2 <= seconds <= 30:
        raise ValueError("La intervención debe durar entre 2 y 30 segundos")
    if float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) < 90:
        raise ValueError("No se detectó voz suficiente en la intervención")
    return torch.from_numpy(samples.copy()).float().div_(32768).unsqueeze(0)


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from speechbrain.inference.speaker import SpeakerRecognition

                _model = SpeakerRecognition.from_hparams(source=MODEL, run_opts={"device": "cpu"})
    return _model


def warmup() -> None:
    """Descarga el modelo antes de iniciar la atención."""
    _get_model()


def verify_many(reference_wavs: list[bytes], spoken_wav: bytes, threshold: float = 0.25) -> dict:
    """Compara una prueba con varias muestras y exige mayoría de coincidencias."""
    if not reference_wavs:
        raise ValueError("No hay muestras de voz enroladas")
    references = [_waveform(content) for content in reference_wavs]
    spoken = _waveform(spoken_wav)
    with _lock:
        model = _get_model()
        results = [model.verify_batch(reference, spoken, threshold=threshold) for reference in references]
    scores = [float(score[0].item()) for score, _ in results]
    matches = [bool(accepted[0].item()) for _, accepted in results]
    required = len(matches) // 2 + 1
    return {"similarity": float(np.median(scores)), "matched": sum(matches) >= required,
            "matches": sum(matches), "samples": len(matches), "required": required,
            "scores": scores, "threshold": threshold, "model": MODEL}


def verify(reference_wav: bytes, spoken_wav: bytes, threshold: float = 0.25) -> dict:
    """Compatibilidad para instalaciones con una única muestra de voz."""
    return verify_many([reference_wav], spoken_wav, threshold)
