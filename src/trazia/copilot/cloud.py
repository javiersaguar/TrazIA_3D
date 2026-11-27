"""Llamadas estructuradas del copiloto con un contexto acotado.

- Datos sintéticos: Groq, si hay `GROQ_API_KEY`.
- Datos del reto: Azure OpenAI de la plataforma de la organización (DEC-03), con el despliegue
  `TRAZIA_COPILOT_DEPLOYMENT` (por defecto `gpt-6-luna`). Pasa por la política de envíos y queda
  en el registro.

Cada usuario elige en Ajustes el modelo preferido (cookie `trazia_modelo`): `auto`, `azure`,
`groq` o `ninguno`. La preferencia solo reordena los proveedores permitidos: nunca salta la
política de envíos, y Groq sigue sin recibir datos del reto.
"""

import json
import os
from contextvars import ContextVar
from urllib.parse import quote, urlencode, urlsplit

import httpx

from trazia.runtime import offline
from trazia.vision import policy
from trazia.vision.base import PolicyError

from .service import CopilotUnavailable

MODEL = "openai/gpt-oss-20b"
PROVIDER = f"groq:{MODEL}"
URL = "https://api.groq.com/openai/v1/chat/completions"


AZURE = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION")
PREFERENCIAS = ("auto", "azure", "groq", "ninguno")
PREFERENCIA: ContextVar[str] = ContextVar("trazia_modelo", default="auto")


def _azure():
    values = [os.environ.get(name, "").strip() for name in AZURE]
    if not all(values):
        return None
    endpoint, key, version = values
    url = urlsplit(endpoint)
    if url.scheme != "https" or not url.hostname or url.path not in ("", "/") or url.query:
        return None
    deployment = os.environ.get("TRAZIA_COPILOT_DEPLOYMENT", "").strip() or "gpt-6-luna"
    query = urlencode({"api-version": version})
    target = f"{endpoint.rstrip('/')}/openai/deployments/{quote(deployment, safe='')}"
    return f"azure-openai:{deployment}", f"{target}/chat/completions?{query}", key


def provider(dataset: str) -> str | None:
    """Proveedor que atendería este conjunto de datos, o None si no hay ninguno permitido."""
    preferencia = PREFERENCIA.get()
    if offline() or preferencia == "ninguno":
        return None
    candidates = []
    if dataset == "synthetic" and os.environ.get("GROQ_API_KEY", "").strip():
        candidates.append(PROVIDER)
    if azure := _azure():
        candidates.append(azure[0])
    if preferencia in ("azure", "groq"):
        candidates.sort(key=lambda name: not name.startswith(preferencia))
    for name in candidates:
        try:
            policy.check_external(name, dataset)
        except PolicyError:
            continue
        return name
    return None


def modelos() -> list[dict]:
    """Opciones de Ajustes, con las que tienen credenciales en este servidor."""
    azure = _azure()
    return [
        {
            "id": "auto",
            "nombre": "Automático",
            "detalle": "Groq para datos sintéticos y Azure OpenAI para los del reto.",
            "disponible": True,
        },
        {
            "id": "azure",
            "nombre": f"Azure OpenAI · {azure[0].split(':', 1)[1]}" if azure else "Azure OpenAI",
            "detalle": "Plataforma de la organización. Admite datos del reto.",
            "disponible": azure is not None,
        },
        {
            "id": "groq",
            "nombre": f"Groq · {MODEL}",
            "detalle": "Solo con datos sintéticos; con datos del reto se usa Azure OpenAI.",
            "disponible": bool(os.environ.get("GROQ_API_KEY", "").strip()),
        },
        {
            "id": "ninguno",
            "nombre": "Sin modelo de lenguaje",
            "detalle": "El copiloto y la voz no envían nada a ningún proveedor.",
            "disponible": True,
        },
    ]


def available(dataset: str) -> bool:
    return provider(dataset) is not None


def structured(system, context, schema, *, dataset, fingerprint, purpose):
    name = provider(dataset)
    if name is None:
        raise CopilotUnavailable("No hay un modelo de lenguaje habilitado para este contexto.")
    if name != PROVIDER:
        return _structured_azure(name, system, context, schema, dataset, fingerprint, purpose)
    try:
        policy.guard_and_log(
            PROVIDER, external=True, dataset=dataset, document_sha256=fingerprint, page_ref=purpose
        )
        response = httpx.post(
            URL,
            headers={
                "Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}",
                "User-Agent": "TrazIA-3D/0.1",
            },
            json={
                "model": MODEL,
                "reasoning_effort": "low",
                "temperature": 0,
                "max_completion_tokens": 900,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": purpose, "strict": True, "schema": schema},
                },
            },
            timeout=httpx.Timeout(6, connect=2.5),
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        payload = response.json()
        choice = payload["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("Respuesta incompleta")
        return json.loads(choice["message"]["content"]), payload.get("usage") or {}
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, OSError) as error:
        raise CopilotUnavailable("Groq no respondió con una salida válida a tiempo.") from error


def _structured_azure(name, system, context, schema, dataset, fingerprint, purpose):
    _, url, key = _azure()
    try:
        policy.guard_and_log(
            name, external=True, dataset=dataset, document_sha256=fingerprint, page_ref=purpose
        )
        response = httpx.post(
            url,
            headers={"api-key": key, "User-Agent": "TrazIA-3D/0.1"},
            json={
                "max_completion_tokens": 900,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": purpose, "strict": True, "schema": schema},
                },
            },
            timeout=httpx.Timeout(10, connect=3),
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        payload = response.json()
        choice = payload["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("Respuesta incompleta")
        return json.loads(choice["message"]["content"]), payload.get("usage") or {}
    except PolicyError as error:
        raise CopilotUnavailable(str(error)) from error
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, OSError) as error:
        mensaje = "Azure OpenAI no respondió con una salida válida a tiempo."
        raise CopilotUnavailable(mensaje) from error


def object_schema(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def enum(values):
    return {"type": "string", "enum": list(values)}
