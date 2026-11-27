"""Claude en Azure AI Foundry, en el mismo proyecto de la organización que Azure OpenAI.

API de mensajes de Anthropic por HTTP con la biblioteca estándar, como el resto de proveedores
de `trazia.vision`. Así funciona igual en el portátil y en Databricks sin otra dependencia.

- `AZURE_ANTHROPIC_ENDPOINT`: URL base del recurso, terminada en `/anthropic`.
- `AZURE_ANTHROPIC_API_KEY`: clave del recurso.
- `AZURE_ANTHROPIC_MODEL`: modelo si no lo fija el enrutador (por defecto `claude-sonnet-5-5`).

El esquema va en el prompt y la respuesta se valida en `_Provider.read`, igual que con Azure
OpenAI. Los esquemas de las tareas no cumplen las restricciones de las salidas estructuradas.
Por eso no se usa `output_config.format`.
"""

import base64
import io
import json
import os
from urllib.parse import urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError

from ..vision.base import RespuestaInvalida, VisionError, VisionUnavailable
from ..vision.providers import _json_from_text, _post_retry, _Provider
from .precios import coste

VERSION_API = "2023-06-01"
# Esfuerzo por modelo: poco razonamiento en el ligero, más en el grande. Se puede cambiar con
# `TRAZIA_AZURE_CLAUDE_ESFUERZO` (low, medium, high).
ESFUERZO = {"claude-haiku-5-5": "low", "claude-sonnet-5-5": "medium", "claude-opus-5-5": "high"}
BOX_FRAME = 1000


def _box_frame(png: bytes) -> tuple[bytes, tuple[int, int]]:
    """Envía un marco donde los píxeles coinciden con la escala 0–1000 del contrato."""
    try:
        with Image.open(io.BytesIO(png)) as image:
            if image.size == (BOX_FRAME, BOX_FRAME):
                return png, image.size
            resized = ImageOps.contain(image.convert("RGB"), (BOX_FRAME, BOX_FRAME))
    except UnidentifiedImageError:
        return png, (BOX_FRAME, BOX_FRAME)
    padded = Image.new("RGB", (BOX_FRAME, BOX_FRAME), "white")
    padded.paste(resized, (0, 0))
    buffer = io.BytesIO()
    padded.save(buffer, format="PNG")
    return buffer.getvalue(), resized.size


def _undo_box_frame(data, size):
    if isinstance(data, dict):
        for key, value in data.items():
            if (
                key in {"bbox", "box_2d"}
                and isinstance(value, list)
                and len(value) == 4
                and all(isinstance(v, (int, float)) for v in value)
            ):
                data[key] = [v * BOX_FRAME / size[i % 2] for i, v in enumerate(value)]
            else:
                _undo_box_frame(value, size)
    elif isinstance(data, list):
        for item in data:
            _undo_box_frame(item, size)


class AzureClaudeProvider(_Provider):
    """Mensajes de Anthropic en Azure AI Foundry con una imagen PNG y respuesta en JSON."""

    external = True
    variables = ("AZURE_ANTHROPIC_ENDPOINT", "AZURE_ANTHROPIC_API_KEY")

    def __init__(self, model: str | None = None, *, dataset: str = "synthetic"):
        super().__init__(dataset=dataset)
        values = {name: os.getenv(name, "").strip() for name in self.variables}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise VisionUnavailable(f"Claude en Azure: faltan {', '.join(missing)}")
        endpoint, self.key = values.values()
        url = urlsplit(endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise VisionUnavailable("Claude en Azure: AZURE_ANTHROPIC_ENDPOINT debe ser HTTPS")
        self.url = endpoint.rstrip("/")
        if not self.url.endswith("/v1/messages"):
            self.url += "/v1/messages"
        self.model = model or os.getenv("AZURE_ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5-5"
        self.name = f"azure-claude:{self.model}"
        self.cache_identity = f"{self.url}#{self.model}/cajas-cuadradas-v1"
        self.esfuerzo = os.getenv("TRAZIA_AZURE_CLAUDE_ESFUERZO", "").strip() or ESFUERZO.get(
            self.model
        )

    def _payload(self, image_png: bytes, prompt: str, schema: dict) -> dict:
        text = f"{prompt}\nJSON Schema of the answer: {json.dumps(schema, separators=(',', ':'))}"
        payload = {
            "model": self.model,
            "max_tokens": 16000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.b64encode(image_png).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": text},
                    ],
                }
            ],
        }
        if self.esfuerzo:
            payload["output_config"] = {"effort": self.esfuerzo}
        return payload

    def _call(self, image_png, prompt, schema):
        headers = {"x-api-key": self.key, "anthropic-version": VERSION_API}
        framed, size = _box_frame(image_png)
        payload = self._payload(framed, prompt, schema)
        try:
            response = _post_retry(self.url, payload, headers)
        except VisionError as exc:
            # Un despliegue que no acepte el esfuerzo responde 400: se repite sin él.
            if "HTTP 400" not in str(exc) or "output_config" not in payload:
                raise
            self.esfuerzo = None
            payload.pop("output_config")
            response = _post_retry(self.url, payload, headers)
        stop = response.get("stop_reason")
        if stop == "refusal":
            categoria = (response.get("stop_details") or {}).get("category")
            raise VisionError(f"{self.name}: el modelo rechazó la petición ({categoria})")
        if stop == "max_tokens":
            raise VisionError(f"{self.name}: respuesta interrumpida (max_tokens)")
        texto = "".join(
            block.get("text", "")
            for block in response.get("content") or []
            if isinstance(block, dict) and block.get("type") == "text"
        )
        try:
            data = _json_from_text(texto)
        except ValueError:
            raise RespuestaInvalida(f"{self.name}: respuesta sin JSON") from None
        usage = response.get("usage") or {}
        _undo_box_frame(data, size)
        tokens_in, tokens_out = usage.get("input_tokens"), usage.get("output_tokens")
        return data, {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_eur": coste(self.model, tokens_in, tokens_out) or 0.0,
        }
