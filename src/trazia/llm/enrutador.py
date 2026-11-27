"""Enrutador único de modelos: cadena de respaldo, niveles por tarea, topes y registro (A7).

Diseño en docs/PLAN.md, sección 7.8. Tiene la misma interfaz que un proveedor de visión
(`read(imagen, tarea, esquema, page_ref=…)`), así que `read_page` y las estrategias lo usan
sin cambios: `get_provider("enrutador")` o `get_provider("enrutador:1")`.

**Cadena.** En nivel 1 Azure OpenAI empieza con Luna. Para lectura compleja (niveles 2–3),
Sonnet en Azure AI Foundry va primero y Sol queda de respaldo. Con datos del reto, habilitar
Sonnet en el enrutador con `TRAZIA_SONNET_DATOS_RETO=1` tras confirmar el uso de Foundry.
Ollama queda después de Azure y Cloudflare solo participa en sintéticos.
Un eslabón sin credenciales se salta con aviso, sin contar como fallo.

**Cuándo se pasa al siguiente proveedor:** error HTTP (429, 5xx, configuración), tiempo
agotado, rechazo del modelo o dos respuestas seguidas fuera de esquema.

**Cuándo se sube de nivel:** la respuesta no es JSON o no cumple el esquema. El llamador también
puede pedir el siguiente nivel con `subir()`, por ejemplo si la confianza queda bajo el umbral o
el validador responde `contradice`. Nunca se sube por defecto.

**Disyuntor.** Tres fallos de un proveedor en dos minutos lo sacan de la cadena cinco minutos.

**Topes.**
- Nivel 3 como máximo `TRAZIA_NIVEL3_MAX` llamadas (5 por defecto) por clave. La clave es la
  revisión si se indica (`Enrutador(clave="BF-V-0016/rev1")`) y, si no, el documento.
- `TRAZIA_PRESUPUESTO_TOKENS`: tokens del proceso. Al llegar al tope ya no se usa el nivel 3 y
  se avisa una vez.

Si ningún proveedor responde se lanza `VisionUnavailable` con el motivo de cada intento.
`read_page` lo anota en `errors` y el campo queda en abstención. No se inventa nada.

**Registro.** Cada llamada resuelta o abstenida se añade a `generated/registro_llm.jsonl` (o
`TRAZIA_REGISTRO_LLM`) con proveedor, nivel, tokens, coste, segundos, caché y respaldo.
`python -m trazia.llm` resume ese registro por nivel.
"""

import json
import os
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..vision import cache
from ..vision.base import (
    PolicyError,
    ProviderResult,
    RespuestaInvalida,
    VisionError,
    VisionUnavailable,
)
from .precios import coste

NIVELES = {
    1: "ligero: nombrar una región, normalizar un texto, respuestas cortas",
    2: "medio: visión por mosaico, validador, respuestas con varias fuentes",
    3: "grande: conflictos que siguen abiertos tras el nivel 2, láminas escaneadas difíciles",
}
# Sol conserva su despliegue como respaldo cuando Sonnet puede leer el documento.
MODELOS_AZURE_OPENAI = {1: "gpt-6-luna", 2: "gpt-6.1-sol", 3: "gpt-6.1-sol"}
MODELOS_CLAUDE = dict.fromkeys(NIVELES, "claude-sonnet-5-5")


def _modelo(familia: str, nivel: int, por_defecto: dict[int, str]) -> str:
    """`TRAZIA_<FAMILIA>_NIVEL<n>` cambia el despliegue o modelo de un nivel."""
    variable = f"TRAZIA_{familia.upper().replace('-', '_')}_NIVEL{nivel}"
    configurado = os.environ.get(variable, "").strip()
    if familia == "azure-claude" and configurado.casefold() in {
        "claude-haiku-5-5",
        "claude-opus-5-5",
    }:
        return por_defecto[nivel]
    return configurado or por_defecto[nivel]


def _azure_openai(nivel: int, dataset: str):
    from ..vision.providers import AzureOpenAIProvider

    return AzureOpenAIProvider(
        dataset=dataset, deployment=_modelo("azure-openai", nivel, MODELOS_AZURE_OPENAI)
    )


def _azure_claude(nivel: int, dataset: str):
    from .claude_azure import AzureClaudeProvider

    return AzureClaudeProvider(_modelo("azure-claude", nivel, MODELOS_CLAUDE), dataset=dataset)


def _ollama(nivel: int, dataset: str):
    from ..vision.providers import OllamaProvider

    # El modelo local es el mismo en todos los niveles: no hay otro en 8 GB de VRAM.
    return OllamaProvider(os.environ.get("TRAZIA_OLLAMA_MODEL", ""), dataset=dataset)


def _cloudflare(nivel: int, dataset: str):
    from ..vision.providers import OpenAICompatibleProvider

    return OpenAICompatibleProvider("cloudflare", dataset=dataset)


@dataclass(frozen=True)
class Eslabon:
    """Un proveedor de la cadena. `crear(nivel, dataset)` devuelve el proveedor de ese nivel."""

    familia: str
    crear: Callable[[int, str], object]
    gratuito: bool = False


CADENA = (
    Eslabon("azure-openai", _azure_openai),
    Eslabon("azure-claude", _azure_claude),
    Eslabon("ollama", _ollama),
    Eslabon("cloudflare", _cloudflare, gratuito=True),
)


class Disyuntor:
    """Saca de la cadena al proveedor que falla `fallos` veces en `ventana` segundos."""

    def __init__(self, fallos: int = 3, ventana: float = 120.0, pausa: float = 300.0, reloj=None):
        self.fallos, self.ventana, self.pausa = fallos, ventana, pausa
        self.reloj = reloj or time.monotonic
        self._fallos: dict[str, deque] = {}
        self._abierto_hasta: dict[str, float] = {}
        self._lock = threading.Lock()

    def disponible(self, familia: str) -> bool:
        with self._lock:
            hasta = self._abierto_hasta.get(familia)
            if hasta is None:
                return True
            if self.reloj() >= hasta:
                del self._abierto_hasta[familia]
                self._fallos.pop(familia, None)
                return True
            return False

    def fallo(self, familia: str) -> bool:
        """Anota un fallo. Devuelve True si con él se abre el disyuntor."""
        with self._lock:
            ahora = self.reloj()
            registro = self._fallos.setdefault(familia, deque())
            registro.append(ahora)
            while registro and ahora - registro[0] > self.ventana:
                registro.popleft()
            if len(registro) >= self.fallos and familia not in self._abierto_hasta:
                self._abierto_hasta[familia] = ahora + self.pausa
                return True
            return False

    def exito(self, familia: str) -> None:
        with self._lock:
            self._fallos.pop(familia, None)

    def reiniciar(self) -> None:
        with self._lock:
            self._fallos.clear()
            self._abierto_hasta.clear()


class Presupuesto:
    """Tokens gastados en el proceso frente a `TRAZIA_PRESUPUESTO_TOKENS` (vacío o 0: sin tope)."""

    def __init__(self):
        self.gastado = 0
        self.avisado = False
        self._lock = threading.Lock()

    @staticmethod
    def tope() -> int | None:
        try:
            valor = int(os.environ.get("TRAZIA_PRESUPUESTO_TOKENS", "0") or 0)
        except ValueError:
            return None
        return valor if valor > 0 else None

    def agotado(self) -> bool:
        tope = self.tope()
        return tope is not None and self.gastado >= tope

    def gastar(self, tokens: int) -> None:
        with self._lock:
            self.gastado += tokens

    def reiniciar(self) -> None:
        with self._lock:
            self.gastado = 0
            self.avisado = False


# Estado del proceso, compartido por todos los enrutadores de un lote.
DISYUNTOR = Disyuntor()
PRESUPUESTO = Presupuesto()
USO_NIVEL3: Counter = Counter()


def reiniciar_estado() -> None:
    """Vacía el disyuntor, el presupuesto y los usos del nivel 3 (pruebas y lotes nuevos)."""
    DISYUNTOR.reiniciar()
    PRESUPUESTO.reiniciar()
    USO_NIVEL3.clear()


def registro_path() -> Path:
    return Path(os.environ.get("TRAZIA_REGISTRO_LLM", "generated/registro_llm.jsonl"))


def _registrar(entrada: dict) -> None:
    path = registro_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entrada = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entrada}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def _tope_nivel3() -> int:
    try:
        return max(0, int(os.environ.get("TRAZIA_NIVEL3_MAX", "5")))
    except ValueError:
        return 5


@dataclass
class Enrutador:
    """Proveedor de visión que reparte cada llamada por la cadena y los niveles."""

    nivel: int = 2
    dataset: str = "synthetic"
    clave: str | None = None
    cadena: tuple[Eslabon, ...] = CADENA
    disyuntor: Disyuntor = field(default_factory=lambda: DISYUNTOR)
    presupuesto: Presupuesto = field(default_factory=lambda: PRESUPUESTO)
    avisos: list[str] = field(default_factory=list)
    external = False  # cada proveedor aplica su política y su registro de envíos

    def __post_init__(self):
        if self.nivel not in NIVELES:
            raise VisionError(f"Nivel {self.nivel} no válido: usa 1, 2 o 3 (el 0 no usa modelo)")
        self.name = f"enrutador:{self.nivel}"
        self.model = ""

    def subir(self) -> "Enrutador":
        """El mismo enrutador un nivel por encima (hasta el 3)."""
        return Enrutador(
            nivel=min(3, self.nivel + 1),
            dataset=self.dataset,
            clave=self.clave,
            cadena=self.cadena,
            disyuntor=self.disyuntor,
            presupuesto=self.presupuesto,
            avisos=self.avisos,
        )

    def _eslabones(self) -> list[Eslabon]:
        sintetico = self.dataset == "synthetic"
        sonnet_permitido = sintetico or (
            self.dataset == "real" and os.environ.get("TRAZIA_SONNET_DATOS_RETO") == "1"
        )
        eslabones = [
            e
            for e in self.cadena
            if (sintetico or not e.gratuito) and (sonnet_permitido or e.familia != "azure-claude")
        ]
        if self.nivel >= 2:
            # Cambia el orden de los dos eslabones de Azure manteniendo el de los demás.
            azure = [
                i for i, e in enumerate(eslabones) if e.familia in {"azure-openai", "azure-claude"}
            ]
            if len(azure) == 2 and eslabones[azure[0]].familia == "azure-openai":
                first, second = azure
                eslabones[first], eslabones[second] = eslabones[second], eslabones[first]
        return eslabones

    def _nivel_maximo(self, clave: str) -> int:
        if self.presupuesto.agotado():
            if not self.presupuesto.avisado:
                self.presupuesto.avisado = True
                self._avisar("Presupuesto de tokens agotado: el enrutador se queda en el nivel 2.")
            return 2
        if USO_NIVEL3[clave] >= _tope_nivel3():
            return 2
        return 3

    def _avisar(self, texto: str) -> None:
        if texto not in self.avisos:
            self.avisos.append(texto)

    def read(
        self, image_png: bytes, task: str, schema: dict | None = None, *, page_ref: str
    ) -> ProviderResult:
        clave = self.clave or page_ref.split("#", 1)[0]
        maximo = self._nivel_maximo(clave)
        inicio = min(self.nivel, maximo)
        motivos: list[str] = []
        for eslabon in self._eslabones():
            if not self.disyuntor.disponible(eslabon.familia):
                motivos.append(f"{eslabon.familia}: fuera de la cadena (disyuntor abierto)")
                continue
            nivel, invalidas = inicio, 0
            while True:
                try:
                    proveedor = eslabon.crear(nivel, self.dataset)
                except VisionUnavailable as exc:
                    motivos.append(f"{eslabon.familia}: {exc}")  # sin credenciales: se salta
                    break
                try:
                    resultado = proveedor.read(image_png, task, schema, page_ref=page_ref)
                except PolicyError as exc:
                    motivos.append(f"{eslabon.familia}: {exc}")
                    break
                except RespuestaInvalida as exc:
                    invalidas += 1
                    motivos.append(f"{eslabon.familia} nivel {nivel}: {exc}")
                    if invalidas >= 2:
                        self._fallo(eslabon.familia)
                        break
                    if nivel < maximo:
                        nivel += 1
                    continue
                except VisionError as exc:
                    motivos.append(f"{eslabon.familia} nivel {nivel}: {exc}")
                    self._fallo(eslabon.familia)
                    break
                self.disyuntor.exito(eslabon.familia)
                return self._resuelto(resultado, eslabon, nivel, clave, task, page_ref, motivos)
        _registrar(
            {
                "estado": "abstencion",
                "nivel_pedido": self.nivel,
                "tarea": task,
                "page_ref": page_ref,
                "dataset": self.dataset,
                "motivos": motivos,
            }
        )
        raise VisionUnavailable("Abstención, ningún proveedor respondió: " + " | ".join(motivos))

    def _fallo(self, familia: str) -> None:
        if cache.offline():
            return  # sin conexión no hay servicio que vigilar
        if self.disyuntor.fallo(familia):
            self._avisar(f"{familia}: 3 fallos en 2 minutos, fuera de la cadena 5 minutos.")

    def _resuelto(self, resultado, eslabon, nivel, clave, task, page_ref, motivos):
        coste_eur = resultado.cost_eur
        conocido = True
        if not resultado.cached:
            if nivel == 3:
                USO_NIVEL3[clave] += 1
            self.presupuesto.gastar((resultado.tokens_in or 0) + (resultado.tokens_out or 0))
            if not coste_eur and eslabon.familia != "ollama":
                calculado = coste(resultado.model, resultado.tokens_in, resultado.tokens_out)
                conocido = calculado is not None
                coste_eur = calculado or 0.0
                resultado.cost_eur = coste_eur
        respaldo = bool(motivos)
        if respaldo:
            resultado.warnings.append(
                f"Respuesta de {resultado.provider} tras {len(motivos)} intento(s) fallido(s)."
            )
        _registrar(
            {
                "estado": "ok",
                "familia": eslabon.familia,
                "proveedor": resultado.provider,
                "modelo": resultado.model,
                "nivel": nivel,
                "nivel_pedido": self.nivel,
                "tarea": task,
                "page_ref": page_ref,
                "dataset": self.dataset,
                "tokens_in": resultado.tokens_in,
                "tokens_out": resultado.tokens_out,
                "coste_eur": round(coste_eur, 6),
                "coste_conocido": conocido,
                "segundos": round(resultado.seconds, 3),
                "cache": resultado.cached,
                "respaldo": respaldo,
                "motivos": motivos,
            }
        )
        return resultado
