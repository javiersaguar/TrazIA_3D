"""Disponibilidad y dictado en el Copiloto."""

from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from trazia.copilot import voice
from trazia.model import Revision

from .copilot_contexts import PROCESS
from .repository import get_revision

router = APIRouter(prefix="/copiloto")
ScopeKind = Literal["revision", "process", "project", "catalogue"]
ScopeId = Annotated[str, Query(min_length=1, max_length=300)]


def _synthetic(request: Request, kind: ScopeKind, identity: str) -> bool:
    if kind == "process":
        return identity in PROCESS
    if kind != "revision":
        return False
    with Session(request.app.state.store.engine) as session:
        try:
            record = get_revision(session, identity)
        except HTTPException as error:
            if error.status_code == 404:
                return False
            raise
        return Revision.model_validate_json(record.payload).dataset == "synthetic"


@router.get("/voice")
def voice_status(request: Request, kind: ScopeKind, identity: ScopeId) -> dict[str, bool]:
    return {"available": bool(voice.free_key()) and _synthetic(request, kind, identity)}


@router.post("/voice")
async def voice_transcript(
    request: Request,
    kind: ScopeKind,
    identity: ScopeId,
    file: Annotated[UploadFile, File()],
) -> dict[str, str]:
    if not voice.free_key():
        raise HTTPException(503, "El dictado gratuito está desactivado.")
    if not await run_in_threadpool(_synthetic, request, kind, identity):
        raise HTTPException(
            403, "El dictado con Groq solo está disponible en contextos sintéticos."
        )
    media_type = (file.content_type or "").partition(";")[0].strip().lower()
    if media_type not in voice.FORMATS:
        raise HTTPException(415, "Formato de audio no admitido para el dictado.")
    audio = await file.read(voice.MAX_AUDIO_BYTES + 1)
    if len(audio) > voice.MAX_AUDIO_BYTES:
        raise HTTPException(413, "La grabación supera el tamaño permitido.")
    signatures = {
        "audio/webm": audio.startswith(b"\x1a\x45\xdf\xa3"),
        "audio/mp4": audio[4:8] == b"ftyp",
        "audio/ogg": audio.startswith(b"OggS"),
    }
    if not signatures[media_type]:
        raise HTTPException(422, "La grabación está vacía o tiene un formato incorrecto.")
    try:
        return {"text": await voice.transcribe(audio, media_type)}
    except voice.VoiceError as error:
        raise HTTPException(error.status, str(error)) from error
