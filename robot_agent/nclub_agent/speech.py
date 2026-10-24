"""Voz en español: VAD y reconocimiento de voz intercambiable.

En el X2 se usa el VAD de AimDK (/agent/process_audio_output, PCM 16 kHz,
16 bits, mono, estados BEGIN/PROCESSING/END). Para micrófonos locales o
pruebas se incluye EnergyVAD. El reconocimiento es un adaptador: faster-whisper
(offline), Vosk (offline, liviano) o Null (sin ASR).
"""

from __future__ import annotations

import io
import logging
import wave
from collections.abc import Iterator
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)
SAMPLE_RATE = 16000

# Valores de AudioVadStateType documentados en AimDK_X2 1.1.0.
VAD_NONE, VAD_BEGIN, VAD_PROCESSING, VAD_END = 0, 1, 2, 3


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


class AimdkVadAssembler:
    """Reúne los fragmentos de ProcessedAudioOutput en una frase completa."""

    def __init__(self, max_seconds: float = 20.0):
        self.buffer = bytearray()
        self.active = False
        self.max_bytes = int(max_seconds * SAMPLE_RATE * 2)
        self.state = VAD_NONE

    def feed(self, vad_state: int, audio: bytes) -> bytes | None:
        self.state = vad_state
        if vad_state == VAD_BEGIN:
            self.buffer = bytearray(audio)
            self.active = True
        elif vad_state == VAD_PROCESSING and self.active:
            if len(self.buffer) + len(audio) <= self.max_bytes:
                self.buffer.extend(audio)
        elif vad_state == VAD_END and self.active:
            self.buffer.extend(audio)
            self.active = False
            utterance, self.buffer = bytes(self.buffer), bytearray()
            return utterance if len(utterance) >= SAMPLE_RATE * 2 * 0.3 else None
        return None


class EnergyVAD:
    """VAD por energía con umbral adaptativo al ruido (marcos de 30 ms)."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, frame_ms: int = 30, ratio: float = 3.0,
                 min_speech_ms: int = 300, hangover_ms: int = 600, max_seconds: float = 20.0):
        self.frame = int(sample_rate * frame_ms / 1000) * 2
        self.ratio = ratio
        self.min_frames = min_speech_ms // frame_ms
        self.hangover = hangover_ms // frame_ms
        self.max_bytes = int(max_seconds * sample_rate * 2)
        self.noise = None
        self.pending = bytearray()
        self.speech = bytearray()
        self.voiced = 0
        self.silent = 0
        self.in_speech = False

    def feed(self, pcm: bytes) -> Iterator[bytes]:
        self.pending.extend(pcm)
        while len(self.pending) >= self.frame:
            chunk = bytes(self.pending[: self.frame])
            del self.pending[: self.frame]
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            energy = float(np.sqrt(np.mean(samples * samples)) + 1e-6)
            if self.noise is None:
                self.noise = energy
            loud = energy > max(self.noise * self.ratio, 200.0)
            if not loud and not self.in_speech:
                self.noise = 0.95 * self.noise + 0.05 * energy
            if loud:
                self.voiced += 1
                self.silent = 0
                if not self.in_speech and self.voiced >= 2:
                    self.in_speech = True
            elif self.in_speech:
                self.silent += 1
            else:
                self.voiced = 0
            if self.in_speech:
                self.speech.extend(chunk)
                if self.silent >= self.hangover or len(self.speech) >= self.max_bytes:
                    utterance, self.speech = bytes(self.speech), bytearray()
                    self.in_speech, self.voiced, self.silent = False, 0, 0
                    if len(utterance) >= self.min_frames * self.frame:
                        yield utterance


class Transcriber(Protocol):
    name: str

    def transcribe(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> tuple[str, float | None]: ...


class NullTranscriber:
    name = "none"

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        return "", None


class FasterWhisperTranscriber:
    """Whisper offline (pip install faster-whisper). 'small' es buen compromiso en CPU."""

    name = "faster-whisper"

    def __init__(self, model: str = "small", device: str = "auto", compute_type: str = "int8"):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self.model.transcribe(audio, language="es", vad_filter=False, beam_size=1)
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()
        confidence = float(np.exp(np.mean([s.avg_logprob for s in segments]))) if segments else None
        return text, confidence


class VoskTranscriber:
    """Vosk offline (pip install vosk + modelo vosk-model-small-es-0.42)."""

    name = "vosk"

    def __init__(self, model_path: str):
        import json

        from vosk import KaldiRecognizer, Model

        self._json = json
        self.model = Model(model_path)
        self._recognizer = KaldiRecognizer

    def transcribe(self, pcm, sample_rate=SAMPLE_RATE):
        recognizer = self._recognizer(self.model, sample_rate)
        recognizer.AcceptWaveform(pcm)
        return self._json.loads(recognizer.FinalResult()).get("text", ""), None


def make_transcriber(engine: str, **options) -> Transcriber:
    try:
        if engine == "faster-whisper":
            return FasterWhisperTranscriber(options.get("model", "small"))
        if engine == "vosk":
            return VoskTranscriber(options["model_path"])
    except Exception as error:  # dependencia o modelo ausente
        log.error("ASR %s no disponible (%s); la voz no se transcribirá.", engine, error)
    return NullTranscriber()
