"""Proveedores de visión con caché, política de envíos y transporte HTTP común."""

import base64
import ipaddress
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import quote, urlencode, urlsplit

from . import cache, policy
from .base import ProviderResult, RespuestaInvalida, VisionError, VisionUnavailable
from .prompts import TASKS, validate

USER_AGENT = "TrazIA-3D/0.1"


def _post(url: str, payload: dict, headers: dict | None = None, timeout: float = 600) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})},
        method="POST",
    )
    try:

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise VisionError(f"{url}: HTTP {exc.code} {detail}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise VisionUnavailable(f"{url}: {exc}") from None


def _scale_boxes(data, factor: float = 1000.0):
    """Cajas 0–1000 → 0–1, recortadas a la imagen y ordenadas (x0 ≤ x1, y0 ≤ y1)."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if key in ("bbox", "box_2d") and isinstance(value, list) and len(value) == 4:
                x0, y0, x1, y1 = (min(1.0, max(0.0, float(v) / factor)) for v in value)
                out["bbox"] = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            else:
                out[key] = _scale_boxes(value, factor)
        return out
    if isinstance(data, list):
        return [_scale_boxes(item, factor) for item in data]
    return data


class _Provider:
    name: str
    model: str
    external: bool

    def __init__(self, *, dataset: str = "synthetic"):
        self.dataset = dataset

    def _call(self, image_png: bytes, prompt: str, schema: dict) -> tuple[dict, dict]:
        raise NotImplementedError

    def read(self, image_png: bytes, task: str, schema: dict | None = None, *, page_ref: str):
        spec = TASKS[task]
        from trazia.feedback import extraction_prompt

        prompt, prompt_sha256 = extraction_prompt(spec)
        schema = schema or spec.schema
        key = cache.cache_key(
            image_png, prompt_sha256, schema, getattr(self, "cache_identity", self.name)
        )
        hit = cache.load(key)
        if hit is not None:
            return hit
        if cache.offline():
            raise VisionUnavailable(f"{self.name}: modo sin conexión y sin respuesta en caché")
        document_sha = page_ref.split("#", 1)[0]
        policy.guard_and_log(
            self.name,
            external=self.external,
            dataset=self.dataset,
            document_sha256=document_sha,
            page_ref=page_ref,
        )
        started = time.perf_counter()
        data, usage = self._call(image_png, prompt, schema)
        errors = validate(data, schema)
        if errors:
            raise RespuestaInvalida(
                f"{self.name}: respuesta fuera de esquema: {'; '.join(errors[:3])}"
            )
        result = ProviderResult(
            data=_scale_boxes(data),
            provider=self.name,
            model=self.model,
            prompt_sha256=prompt_sha256,
            seconds=usage.get("seconds", time.perf_counter() - started),
            tokens_in=usage.get("tokens_in"),
            tokens_out=usage.get("tokens_out"),
            cost_eur=usage.get("cost_eur", 0.0),
            external=self.external,
        )
        cache.store(key, result)
        return result


class OllamaProvider(_Provider):
    """Modelo local servido por Ollama. No sale nada del equipo; coste 0 €."""

    external = False

    def __init__(
        self, model: str = "qwen3-vl:4b-instruct", *, dataset: str = "synthetic", host=None
    ):
        super().__init__(dataset=dataset)
        self.model = model or os.environ.get("TRAZIA_OLLAMA_MODEL", "qwen3-vl:4b-instruct")
        self.name = f"ollama:{self.model}"
        self.host = (
            host
            or os.environ.get("TRAZIA_OLLAMA_URL")
            or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ).rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        url = urlsplit(self.host)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise VisionUnavailable("Ollama: URL de servicio inválida")
        try:
            local = ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            local = url.hostname in ("localhost", "ollama", "host.docker.internal")
        self.external = not local
        self.cache_identity = f"{self.name}@{self.host}"

    def _call(self, image_png, prompt, schema):
        details = _post(f"{self.host}/api/show", {"model": self.model})
        if details.get("remote_host") or details.get("remote_model"):
            raise VisionUnavailable("Ollama: se requieren pesos locales, sin modelo cloud")
        if details.get("details", {}).get("format") != "gguf" or "vision" not in details.get(
            "capabilities", []
        ):
            raise VisionUnavailable("Ollama: no se pudo verificar un modelo visual local")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image_png).decode("ascii")],
                }
            ],
            "format": schema,
            "stream": False,
            "think": False,
            "keep_alive": "15m",
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 4096},
        }
        response = _post(f"{self.host}/api/chat", payload)
        try:
            data = json.loads(response["message"]["content"])
        except (KeyError, json.JSONDecodeError) as exc:
            raise RespuestaInvalida(f"{self.name}: respuesta no es JSON ({exc})") from None
        return data, {
            "seconds": response.get("total_duration", 0) / 1e9,
            "tokens_in": response.get("prompt_eval_count"),
            "tokens_out": response.get("eval_count"),
            "cost_eur": 0.0,
        }


def _price(env: str, default: float) -> float:
    """Precio en € por millón de tokens, configurable porque cambia: revisar antes del pitch."""
    try:
        return float(os.environ.get(env, default))
    except ValueError:
        return default


RETRY_WAITS = (0.5, 1.0, 2.0)


def _post_retry(url: str, payload: dict, headers: dict | None = None) -> dict:
    """`_post` con reintentos cuando el servicio pide esperar (límite de tasa o saturación)."""
    for wait in (*RETRY_WAITS, None):
        try:
            return _post(url, payload, headers)
        except VisionError as exc:
            if wait is None or not any(f"HTTP {c}" in str(exc) for c in (429, 503)):
                raise
            time.sleep(wait)
    raise AssertionError("inalcanzable")


def _json_from_text(text: str) -> dict:
    """JSON de una respuesta de chat: sin razonamiento `<think>` ni vallas ```json."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("sin objeto JSON", text, 0)
    return json.loads(text[start : end + 1])


# Servicios con la API de chat de OpenAI: URL, variable de la clave y modelo por defecto.
OPENAI_COMPATIBLE = {
    "cloudflare": (
        "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
        "CLOUDFLARE_API_TOKEN",
        "@cf/meta/llama-3.2-11b-vision-instruct",
    ),
}
# Cómo se pide JSON, de más a menos estricto. Si el modelo rechaza un modo, se pasa al siguiente
# y se recuerda para las siguientes llamadas.
JSON_MODES = ("json_schema", "json_object", "texto")


class OpenAICompatibleProvider(_Provider):
    """Cloudflare Workers AI con el formato de chat de OpenAI.

    Externos: solo sintéticos salvo autorización (DEC-03). Coste 0 € por defecto porque se usan
    las cuotas gratuitas; con `<SERVICIO>_EUR_PER_MTOK_IN/OUT` se fija el precio de pago.
    """

    external = True

    def __init__(self, family: str, model: str | None = None, *, dataset: str = "synthetic"):
        super().__init__(dataset=dataset)
        url, key_env, default = OPENAI_COMPATIBLE[family]
        self.family = family
        self.model = model or os.environ.get(f"{family.upper()}_MODEL", default)
        self.name = f"{family}:{self.model}"
        self.key = os.environ.get(key_env)
        if family == "cloudflare":
            account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
            url = url.format(account=account) if account else ""
        self.url = url
        self.mode = 0
        if (not self.key or not self.url) and not cache.offline():
            raise VisionUnavailable(f"{family}: falta {key_env} en .env")

    def _payload(self, image_png: bytes, prompt: str, schema: dict) -> dict:
        mode = JSON_MODES[self.mode]
        text = prompt
        if mode != "json_schema":
            text += "\nJSON Schema of the answer: " + json.dumps(schema, separators=(",", ":"))
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(image_png).decode("ascii")
                            },
                        },
                    ],
                }
            ],
        }
        if mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "lectura", "schema": schema, "strict": True},
            }
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _call(self, image_png, prompt, schema):
        if not self.key or not self.url:
            raise VisionUnavailable(f"{self.family}: falta la clave")
        started = time.perf_counter()
        while True:
            try:
                response = _post_retry(
                    self.url,
                    self._payload(image_png, prompt, schema),
                    {"Authorization": f"Bearer {self.key}"},
                )
                break
            except VisionError as exc:
                rejected = "HTTP 400" in str(exc) or "HTTP 422" in str(exc)
                if not rejected or self.mode == len(JSON_MODES) - 1:
                    raise
                self.mode += 1  # el modelo no acepta este modo de JSON: probar el siguiente
        try:
            content = response["choices"][0]["message"]["content"]
            data = _json_from_text(content) if isinstance(content, str) else content
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RespuestaInvalida(f"{self.name}: respuesta inesperada ({exc})") from None
        usage = response.get("usage") or {}
        tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        prefix = self.family.upper()
        cost = (tokens_in or 0) / 1e6 * _price(f"{prefix}_EUR_PER_MTOK_IN", 0.0) + (
            tokens_out or 0
        ) / 1e6 * _price(f"{prefix}_EUR_PER_MTOK_OUT", 0.0)
        return data, {
            "seconds": time.perf_counter() - started,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_eur": cost,
        }


def _openai_compatible(family: str) -> Callable[..., _Provider]:
    def factory(model: str | None = None, *, dataset: str = "synthetic") -> _Provider:
        return OpenAICompatibleProvider(family, model, dataset=dataset)

    return factory


class AzureOpenAIProvider(_Provider):
    """Chat Completions de Azure OpenAI con un despliegue de visión."""

    external = True
    variables = (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_API_KEY",
    )

    def __init__(self, *, dataset: str = "synthetic", deployment: str | None = None):
        """`deployment` sustituye a `AZURE_OPENAI_DEPLOYMENT` (niveles del enrutador)."""
        super().__init__(dataset=dataset)
        values = {name: os.getenv(name, "").strip() for name in self.variables}
        if deployment:
            values["AZURE_OPENAI_DEPLOYMENT"] = deployment
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise VisionUnavailable(f"Azure OpenAI: faltan {', '.join(missing)}")
        endpoint, self.model, version, self.key = values.values()
        url = urlsplit(endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise VisionUnavailable(
                "Azure OpenAI: AZURE_OPENAI_ENDPOINT debe ser una URL HTTPS base"
            )
        deployment = quote(self.model, safe="")
        query = urlencode({"api-version": version})
        self.url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?{query}"
        )
        self.name = f"azure-openai:{self.model}"
        self.cache_identity = self.url

    def _call(self, image_png, prompt, schema):
        image = base64.b64encode(image_png).decode("ascii")
        text = f"{prompt}\nJSON Schema of the answer: {json.dumps(schema, separators=(',', ':'))}"
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image}"},
                        },
                    ],
                }
            ],
            "max_completion_tokens": 8192,
        }
        response = _post_retry(self.url, payload, {"api-key": self.key})
        try:
            choice = response["choices"][0]
            finish = choice.get("finish_reason")
            if finish in {"length", "content_filter"}:
                raise VisionError(f"{self.name}: respuesta interrumpida ({finish})")
            data = _json_from_text(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
            raise RespuestaInvalida(f"{self.name}: respuesta de Azure no válida") from exc
        usage = response.get("usage") or {}
        return data, {
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens"),
        }


FACTORIES: dict[str, Callable[..., _Provider]] = {
    family: _openai_compatible(family) for family in OPENAI_COMPATIBLE
}


def get_provider(spec: str, *, dataset: str = "synthetic"):
    """Resuelve un proveedor por su nombre.

    - `enrutador` o `enrutador:<nivel>`: cadena con respaldo y niveles (`trazia.llm`).
    - `azure-openai`, `azure-claude[:modelo]`, `ollama[:modelo]` y `cloudflare[:modelo]`.
    """
    family, _, model = spec.partition(":")
    if family == "enrutador":
        from ..llm import Enrutador

        return Enrutador(nivel=int(model) if model else 2, dataset=dataset)
    if family == "azure-claude":
        from ..llm.claude_azure import AzureClaudeProvider

        return AzureClaudeProvider(model or None, dataset=dataset)
    if family == "ollama":
        return OllamaProvider(model or os.environ.get("TRAZIA_OLLAMA_MODEL", ""), dataset=dataset)
    if family in {"azure", "azure-openai"}:
        if model:
            raise VisionError("Configura el despliegue con AZURE_OPENAI_DEPLOYMENT")
        return AzureOpenAIProvider(dataset=dataset)
    if family not in FACTORIES:
        raise VisionError(f"Proveedor de visión desconocido: {spec}")
    return FACTORIES[family](model or None, dataset=dataset)
