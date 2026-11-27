"""Transcripción de clips sintéticos con una clave Groq Free dedicada."""

import asyncio
import hashlib
import os

import httpx

from trazia.runtime import offline
from trazia.vision import policy
from trazia.vision.base import PolicyError

MODEL = "whisper-large-v3-turbo"
PROVIDER = f"groq:{MODEL}"
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_AUDIO_BYTES = 512 * 1024
FORMATS = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg"}


class VoiceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status


def free_key() -> str:
    if offline() or os.getenv("TRAZIA_VOICE_GROQ_FREE") != "1":
        return ""
    try:
        policy.check_external(PROVIDER, "synthetic")
    except PolicyError:
        return ""
    key = os.getenv("GROQ_VOICE_FREE_API_KEY", "").strip()
    return key if key != os.getenv("GROQ_API_KEY", "").strip() else ""


async def transcribe(audio: bytes, media_type: str, *, transport=None) -> str:
    key = free_key()
    if not key:
        raise VoiceError(503, "El dictado gratuito está desactivado.")
    filename = f"dictado.{FORMATS[media_type]}"
    try:
        policy.guard_and_log(
            PROVIDER,
            external=True,
            dataset="synthetic",
            document_sha256=hashlib.sha256(audio).hexdigest(),
            page_ref="copiloto.dictado",
        )
        async with (
            asyncio.timeout(12),
            httpx.AsyncClient(
                timeout=httpx.Timeout(10, connect=3),
                trust_env=False,
                transport=transport,
            ) as client,
        ):
            response = await client.post(
                URL,
                headers={"Authorization": f"Bearer {key}"},
                data={"model": MODEL, "language": "es", "temperature": "0"},
                files={"file": (filename, audio, media_type)},
            )
        if response.status_code == 429:
            raise VoiceError(
                429, "Se alcanzó el límite gratuito de Groq. Puedes escribir el mensaje."
            )
        response.raise_for_status()
        transcript = response.json()["text"].strip()
    except (
        httpx.HTTPError,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    ) as error:
        raise VoiceError(
            502, "Groq no pudo transcribir el audio. Puedes escribir el mensaje."
        ) from error
    except (OSError, PolicyError) as error:
        raise VoiceError(503, "El dictado gratuito está desactivado.") from error
    if not transcript:
        raise VoiceError(422, "No se detectó voz. Prueba a grabar de nuevo.")
    if len(transcript) > 2000:
        raise VoiceError(422, "El dictado es demasiado largo. Prueba con una grabación más corta.")
    return transcript
