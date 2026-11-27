"""Enrutador de modelos (PLAN 7.8): respaldo, niveles, disyuntor, topes y registro, sin red."""

import json
from io import BytesIO

import pytest
from PIL import Image

from trazia.llm import (
    Disyuntor,
    Enrutador,
    Eslabon,
    Presupuesto,
    claude_azure,
    enrutador,
    informe,
    reiniciar_estado,
)
from trazia.vision import PolicyError, VisionError, VisionUnavailable, providers
from trazia.vision.providers import _Provider
from trazia.vision.reader import read_page

RESPUESTA = {"items": [{"text": "N1", "bbox": [100, 200, 300, 260]}]}


class Falso(_Provider):
    """Proveedor de prueba: `comportamiento(nivel)` devuelve la respuesta o lanza el error."""

    def __init__(self, familia, nivel, comportamiento, llamadas, *, external, dataset):
        super().__init__(dataset=dataset)
        self.external = external
        self.model = f"{familia}-n{nivel}"
        self.name = f"{familia}:{self.model}"
        self.nivel = nivel
        self.comportamiento = comportamiento
        self.llamadas = llamadas

    def _call(self, image_png, prompt, schema):
        self.llamadas.append(self.name)
        respuesta = self.comportamiento(self.nivel)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta, {"tokens_in": 100 * self.nivel, "tokens_out": 10, "cost_eur": 0.0}


def eslabon(familia, comportamiento, llamadas, *, gratuito=False, external=False):
    return Eslabon(
        familia,
        lambda nivel, dataset: Falso(
            familia, nivel, comportamiento, llamadas, external=external, dataset=dataset
        ),
        gratuito=gratuito,
    )


def responde(nivel):
    return RESPUESTA


def caido(nivel):
    return VisionError("https://servicio: HTTP 503 saturado")


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAZIA_VISION_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("TRAZIA_REGISTRO_ENVIOS", str(tmp_path / "envios.jsonl"))
    monkeypatch.setenv("TRAZIA_REGISTRO_LLM", str(tmp_path / "llm.jsonl"))
    for nombre in (
        "TRAZIA_VISION_OFFLINE",
        "TRAZIA_EXTERNAL_PROVIDERS",
        "TRAZIA_EXTERNAL_AUTH",
        "TRAZIA_PRESUPUESTO_TOKENS",
        "TRAZIA_NIVEL3_MAX",
        "TRAZIA_SONNET_DATOS_RETO",
    ):
        monkeypatch.delenv(nombre, raising=False)
    reiniciar_estado()
    yield tmp_path
    reiniciar_estado()


def registro(tmp_path) -> list[dict]:
    path = tmp_path / "llm.jsonl"
    return [json.loads(linea) for linea in path.read_text(encoding="utf-8").splitlines()]


def nuevo(cadena, **kwargs) -> Enrutador:
    return Enrutador(
        cadena=tuple(cadena), disyuntor=Disyuntor(), presupuesto=Presupuesto(), **kwargs
    )


def test_un_503_pasa_al_siguiente_proveedor(aislado):
    llamadas = []
    ruta = nuevo([eslabon("a", caido, llamadas), eslabon("b", responde, llamadas)])
    resultado = ruta.read(b"png", "lineas", page_ref="doc#p1")
    assert llamadas == ["a:a-n2", "b:b-n2"]
    assert resultado.provider == "b:b-n2" and resultado.data["items"][0]["text"] == "N1"
    (entrada,) = registro(aislado)
    assert entrada["estado"] == "ok" and entrada["respaldo"] and entrada["nivel"] == 2
    assert entrada["tokens_in"] == 200 and "HTTP 503" in entrada["motivos"][0]


@pytest.mark.parametrize(
    "dataset,nivel,permiso,esperado",
    [
        ("synthetic", 1, False, "azure-openai"),
        ("synthetic", 2, False, "azure-claude"),
        ("synthetic", 3, False, "azure-claude"),
        ("real", 2, False, "azure-openai"),
        ("real", 2, True, "azure-claude"),
        ("real", 3, True, "azure-claude"),
    ],
)
def test_prioridad_sonnet_segun_nivel_y_dataset(monkeypatch, dataset, nivel, permiso, esperado):
    if permiso:
        monkeypatch.setenv("TRAZIA_SONNET_DATOS_RETO", "1")
    llamadas = []
    cadena = [
        eslabon("azure-openai", responde, llamadas),
        eslabon("azure-claude", responde, llamadas),
    ]
    resultado = nuevo(cadena, nivel=nivel, dataset=dataset).read(b"png", "lineas", page_ref="test")
    assert llamadas == [resultado.provider] and resultado.provider.startswith(f"{esperado}:")


def test_sonnet_caido_pasa_a_sol(aislado):
    llamadas = []
    ruta = nuevo(
        [eslabon("azure-openai", responde, llamadas), eslabon("azure-claude", caido, llamadas)]
    )
    respuesta = ruta.read(b"imagen", "lineas", page_ref="sintetico#p1")
    assert respuesta.provider == "azure-openai:azure-openai-n2"
    assert llamadas == ["azure-claude:azure-claude-n2", respuesta.provider]
    assert registro(aislado)[0]["respaldo"]


def test_un_json_fuera_de_esquema_sube_de_nivel(aislado):
    llamadas = []
    ruta = nuevo([eslabon("a", lambda n: {"otra": 1} if n == 2 else RESPUESTA, llamadas)])
    resultado = ruta.read(b"png", "lineas", page_ref="doc#p1")
    assert llamadas == ["a:a-n2", "a:a-n3"] and resultado.model == "a-n3"
    assert registro(aislado)[0]["nivel"] == 3


def test_dos_respuestas_invalidas_seguidas_pasan_al_siguiente(aislado):
    llamadas = []
    ruta = nuevo([eslabon("a", lambda n: {"otra": 1}, llamadas), eslabon("b", responde, llamadas)])
    assert ruta.read(b"png", "lineas", page_ref="doc#p1").provider == "b:b-n2"
    assert llamadas == ["a:a-n2", "a:a-n3", "b:b-n2"]


def test_con_datos_reales_nunca_se_llama_a_un_gratuito(aislado):
    llamadas = []
    ruta = nuevo(
        [eslabon("a", caido, llamadas), eslabon("gratis", responde, llamadas, gratuito=True)],
        dataset="real",
    )
    with pytest.raises(VisionUnavailable, match="Abstención"):
        ruta.read(b"png", "lineas", page_ref="doc#p1")
    assert llamadas == ["a:a-n2"]
    assert registro(aislado)[0]["estado"] == "abstencion"
    sintetico = nuevo(
        [eslabon("a", caido, []), eslabon("gratis", responde, llamadas, gratuito=True)]
    )
    assert sintetico.read(b"png", "lineas", page_ref="doc#p2").provider == "gratis:gratis-n2"


def test_el_disyuntor_se_abre_y_se_cierra():
    ahora = [0.0]
    disyuntor = Disyuntor(reloj=lambda: ahora[0])
    assert not disyuntor.fallo("a") and not disyuntor.fallo("a")
    assert disyuntor.fallo("a") and not disyuntor.disponible("a")
    ahora[0] = 299.0
    assert not disyuntor.disponible("a")
    ahora[0] = 301.0
    assert disyuntor.disponible("a")
    ahora[0] = 400.0
    disyuntor.fallo("a")
    ahora[0] = 530.0  # el fallo de 400 s ya ha salido de la ventana de dos minutos
    assert not disyuntor.fallo("a") and not disyuntor.fallo("a")
    assert disyuntor.disponible("a")


def test_el_disyuntor_abierto_saca_al_proveedor_de_la_cadena(aislado):
    llamadas = []
    ruta = nuevo([eslabon("a", caido, llamadas), eslabon("b", responde, llamadas)])
    for pagina in range(3):
        ruta.read(bytes([pagina]), "lineas", page_ref=f"doc#p{pagina}")
    assert llamadas.count("a:a-n2") == 3
    assert any("fuera de la cadena" in aviso for aviso in ruta.avisos)
    ruta.read(b"otra", "lineas", page_ref="doc#p9")
    assert llamadas.count("a:a-n2") == 3 and llamadas[-1] == "b:b-n2"


def test_sin_credenciales_se_salta_sin_abrir_el_disyuntor(aislado):
    def sin_clave(nivel, dataset):
        raise VisionUnavailable("Azure OpenAI: faltan AZURE_OPENAI_API_KEY")

    llamadas = []
    ruta = nuevo([Eslabon("azure", sin_clave), eslabon("b", responde, llamadas)])
    for pagina in range(4):
        ruta.read(b"png", "lineas", page_ref=f"doc#p{pagina}")
    assert ruta.disyuntor.disponible("azure") and not ruta.avisos


def test_la_politica_corta_un_externo_sin_tumbar_la_cadena(aislado):
    llamadas = []
    ruta = nuevo(
        [eslabon("ext", responde, llamadas, external=True), eslabon("b", responde, llamadas)],
        dataset="real",
    )
    assert ruta.read(b"png", "lineas", page_ref="doc#p1").provider == "b:b-n2"
    assert llamadas == ["b:b-n2"]


def test_tope_de_llamadas_de_nivel_3_por_revision(aislado, monkeypatch):
    monkeypatch.setenv("TRAZIA_NIVEL3_MAX", "2")
    ruta = nuevo([eslabon("a", responde, [])], nivel=3, clave="BF-V-0016/rev1")
    niveles = [ruta.read(bytes([i]), "lineas", page_ref=f"x#p{i}").model for i in range(3)]
    assert niveles == ["a-n3", "a-n3", "a-n2"]
    otra = nuevo([eslabon("a", responde, [])], nivel=3, clave="BF-V-0016/rev2")
    assert otra.read(b"z", "lineas", page_ref="x#p1").model == "a-n3"


def test_presupuesto_agotado_se_queda_en_el_nivel_2(aislado, monkeypatch):
    monkeypatch.setenv("TRAZIA_PRESUPUESTO_TOKENS", "300")
    ruta = nuevo([eslabon("a", responde, [])], nivel=3)
    assert ruta.read(b"1", "lineas", page_ref="d#p1").model == "a-n3"  # 310 tokens
    assert ruta.read(b"2", "lineas", page_ref="d#p2").model == "a-n2"
    assert ruta.avisos == ["Presupuesto de tokens agotado: el enrutador se queda en el nivel 2."]


def test_la_cache_no_gasta_presupuesto_ni_vuelve_a_llamar(aislado):
    llamadas = []
    ruta = nuevo([eslabon("a", responde, llamadas)])
    ruta.read(b"png", "lineas", page_ref="d#p1")
    segunda = ruta.read(b"png", "lineas", page_ref="d#p1")
    assert segunda.cached and llamadas == ["a:a-n2"] and ruta.presupuesto.gastado == 210
    assert [e["cache"] for e in registro(aislado)] == [False, True]


def test_subir_pide_el_siguiente_nivel(aislado):
    ruta = nuevo([eslabon("a", responde, [])], nivel=1)
    assert ruta.subir().nivel == 2 and ruta.subir().subir().subir().nivel == 3
    with pytest.raises(VisionError):
        Enrutador(nivel=0)


def test_cadena_por_defecto_con_azure_apagado_se_abstiene_sin_excepciones(aislado, monkeypatch):
    """Lo que pide el «hecho» de 7.8: Azure con las variables vacías no rompe nada."""
    for nombre in (
        *providers.AzureOpenAIProvider.variables,
        *claude_azure.AzureClaudeProvider.variables,
    ):
        monkeypatch.setenv(nombre, "")
    monkeypatch.setenv("TRAZIA_VISION_OFFLINE", "1")  # Ollama sin caché tampoco responde
    pagina = Image.new("RGB", (1600, 800), "white")
    lectura = read_page(Enrutador(dataset="real"), pagina, page_ref="doc#p1", tile_size=1280)
    assert lectura.items == [] and lectura.errors
    assert all("Abstención" in error for error in lectura.errors)
    assert "cloudflare" not in " ".join(lectura.errors)  # datos reales: sin gratuitos


def test_read_page_con_el_enrutador_suma_los_mosaicos(aislado):
    llamadas = []
    ruta = nuevo([eslabon("a", caido, llamadas), eslabon("b", responde, llamadas)])
    pagina = Image.linear_gradient("L").rotate(90).resize((2400, 1200)).convert("RGB")
    lectura = read_page(ruta, pagina, page_ref="doc#p1", tile_size=1280)
    assert lectura.items and not lectura.errors and lectura.provider == "b:b-n2"
    assert lectura.tokens_in == 200 * lectura.tiles


def test_get_provider_resuelve_enrutador_ollama_y_claude(monkeypatch):
    ruta = providers.get_provider("enrutador:1", dataset="real")
    assert isinstance(ruta, Enrutador) and ruta.nivel == 1 and ruta.dataset == "real"
    assert providers.get_provider("enrutador").nivel == 2
    assert providers.get_provider("ollama").name.startswith("ollama:")
    monkeypatch.setenv(
        "AZURE_ANTHROPIC_ENDPOINT", "https://recurso.services.ai.azure.com/anthropic"
    )
    monkeypatch.setenv("AZURE_ANTHROPIC_API_KEY", "clave")
    claude = providers.get_provider("azure-claude:claude-haiku-5-5")
    assert claude.name == "azure-claude:claude-haiku-5-5"
    assert claude.url == "https://recurso.services.ai.azure.com/anthropic/v1/messages"


def test_azure_openai_acepta_el_despliegue_del_nivel(monkeypatch):
    for nombre in providers.AzureOpenAIProvider.variables:
        monkeypatch.setenv(nombre, "https://r.openai.azure.com" if "ENDPOINT" in nombre else "x")
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT")
    proveedor = enrutador._azure_openai(1, "real")
    assert proveedor.name == "azure-openai:gpt-6-luna"
    assert "/deployments/gpt-6-luna/" in proveedor.url
    monkeypatch.setenv("TRAZIA_AZURE_OPENAI_NIVEL1", "mi-gpt")
    assert enrutador._azure_openai(1, "real").model == "mi-gpt"


def test_el_respaldo_claude_migra_las_preferencias_antiguas_a_sonnet(monkeypatch):
    monkeypatch.delenv("TRAZIA_AZURE_CLAUDE_NIVEL2", raising=False)
    monkeypatch.setenv("TRAZIA_AZURE_CLAUDE_NIVEL1", "claude-haiku-5-5")
    monkeypatch.setenv("TRAZIA_AZURE_CLAUDE_NIVEL3", "claude-opus-5-5")
    for nivel in enrutador.NIVELES:
        assert (
            enrutador._modelo("azure-claude", nivel, enrutador.MODELOS_CLAUDE)
            == "claude-sonnet-5-5"
        )


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv(
        "AZURE_ANTHROPIC_ENDPOINT", "https://recurso.services.ai.azure.com/anthropic"
    )
    monkeypatch.setenv("AZURE_ANTHROPIC_API_KEY", "clave")
    monkeypatch.delenv("TRAZIA_AZURE_CLAUDE_ESFUERZO", raising=False)
    monkeypatch.delenv("TRAZIA_EUR_POR_USD", raising=False)
    enviados = []

    def simular(respuesta):
        def post(url, payload, headers=None):
            enviados.append((url, payload, headers))
            if isinstance(respuesta, Exception):
                raise respuesta
            return respuesta

        monkeypatch.setattr(claude_azure, "_post_retry", post)

    return simular, enviados


def test_claude_en_azure_envia_la_imagen_y_lee_el_uso(aislado, claude):
    simular, enviados = claude
    simular(
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps(RESPUESTA)}],
            "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000},
        }
    )
    resultado = claude_azure.AzureClaudeProvider("claude-haiku-5-5", dataset="real").read(
        b"png", "lineas", page_ref="doc#p1"
    )
    url, payload, headers = enviados[0]
    assert url.endswith("/anthropic/v1/messages") and headers["anthropic-version"]
    assert payload["model"] == "claude-haiku-5-5" and "temperature" not in payload
    assert payload["output_config"] == {"effort": "low"}
    imagen, texto = payload["messages"][0]["content"]
    assert imagen["type"] == "image" and imagen["source"]["media_type"] == "image/png"
    assert "JSON Schema" in texto["text"]
    assert resultado.data["items"][0]["bbox"] == [0.1, 0.2, 0.3, 0.26]
    assert resultado.cost_eur == pytest.approx(0.10 + 0.05)
    envio = json.loads((aislado / "envios.jsonl").read_text(encoding="utf-8"))
    assert envio["provider"] == "azure-claude:claude-haiku-5-5" and envio["dataset"] == "real"


def test_claude_reproyecta_la_cita_al_recorte_rectangular(claude):
    import base64

    simular, enviados = claude
    rectangulo = BytesIO()
    Image.new("RGB", (1000, 500), "white").save(rectangulo, format="PNG")
    simular(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"items": [{"text": "N1", "bbox": [100, 100, 300, 200]}]}),
                }
            ]
        }
    )
    salida = claude_azure.AzureClaudeProvider().read(
        rectangulo.getvalue(), "lineas", page_ref="doc"
    )
    image = enviados[0][1]["messages"][0]["content"][0]
    assert Image.open(BytesIO(base64.b64decode(image["source"]["data"]))).size == (1000, 1000)
    assert salida.data["items"][0]["bbox"] == pytest.approx([0.1, 0.2, 0.3, 0.4])


def test_claude_rechazo_y_corte_son_errores_del_proveedor(aislado, claude):
    simular, _ = claude
    proveedor = claude_azure.AzureClaudeProvider(dataset="synthetic")
    simular({"stop_reason": "refusal", "stop_details": {"category": "cyber"}, "content": []})
    with pytest.raises(VisionError, match="rechazó"):
        proveedor.read(b"a", "lineas", page_ref="d#p1")
    simular({"stop_reason": "max_tokens", "content": [{"type": "text", "text": "{"}]})
    with pytest.raises(VisionError, match="interrumpida"):
        proveedor.read(b"b", "lineas", page_ref="d#p1")


def test_claude_repite_sin_esfuerzo_si_el_despliegue_no_lo_acepta(aislado, claude, monkeypatch):
    enviados = []
    respuestas = [
        VisionError("https://x: HTTP 400 output_config not supported"),
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(RESPUESTA)}]},
    ]

    def post(url, payload, headers=None):
        enviados.append(dict(payload))
        respuesta = respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(claude_azure, "_post_retry", post)
    claude_azure.AzureClaudeProvider().read(b"png", "lineas", page_ref="d#p1")
    assert "output_config" in enviados[0] and "output_config" not in enviados[1]


def test_la_politica_admite_claude_de_la_plataforma_con_datos_reales(aislado, monkeypatch):
    from trazia.vision import policy

    monkeypatch.setenv("TRAZIA_EXTERNAL_PROVIDERS", "synthetic_only")
    assert policy.check_external("azure-claude:claude-sonnet-5-5", "real") is None
    with pytest.raises(PolicyError):
        policy.check_external("cloudflare:modelo", "real")


def test_informe_por_nivel_y_ahorro_frente_al_nivel_3(aislado, monkeypatch):
    monkeypatch.delenv("TRAZIA_AZURE_CLAUDE_NIVEL3", raising=False)
    entradas = [
        {
            "estado": "ok",
            "familia": "azure-claude",
            "proveedor": "azure-claude:claude-haiku-5-5",
            "modelo": "claude-haiku-5-5",
            "nivel": 1,
            "tokens_in": 1_000_000,
            "tokens_out": 0,
            "coste_eur": 0.10,
            "coste_conocido": True,
            "segundos": 2.0,
            "cache": False,
            "respaldo": True,
        },
        {
            "estado": "ok",
            "familia": "azure-openai",
            "proveedor": "azure-openai:gpt-6-luna",
            "modelo": "gpt-6-luna",
            "nivel": 1,
            "tokens_in": 10,
            "tokens_out": 1,
            "coste_eur": 0.0,
            "coste_conocido": False,
            "segundos": 1.0,
            "cache": False,
            "respaldo": False,
        },
        {"estado": "abstencion", "nivel_pedido": 2},
    ]
    resumen = informe.resumen_por_nivel(entradas)
    fila = resumen["niveles"][1]
    assert fila["llamadas"] == 2 and fila["respaldos"] == 1 and fila["sin_precio"] == 1
    assert fila["coste_eur"] == pytest.approx(0.10)
    assert fila["coste_si_nivel3_eur"] == pytest.approx(2.0)  # Sonnet: 2 € por millón de entrada
    assert resumen["abstenciones"] == 1
    path = aislado / "llm.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entradas) + "\n", encoding="utf-8")
    assert informe.main([str(path)]) == 0
