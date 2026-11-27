"""Prueba de los servicios de Azure del equipo (guía de la plataforma, sección 17).

    python scripts/probar_azure.py                 # todos los servicios con datos en .env
    python scripts/probar_azure.py --solo anthropic  # uno: openai, anthropic, layout, search...
    python scripts/probar_azure.py --env ../TrazIA-3D-lectura/.env

Código de salida: 0 si todo lo pedido responde, 1 si algo falla, 2 si alguno se salta por
falta de credenciales (0 con `--permitir-saltos`). La prueba de chat exige `json_schema`
estricto y comprueba que la línea citada contiene el valor.

Las claves y los endpoints están en el PDF de accesos del canal general de Teams, como enlaces
a 1Password. Se copian a `.env` (ignorado por Git) y nunca al código, a Teams ni a un commit.
Este script no imprime ninguna clave: solo el servicio, si responde y lo que tarda.

Solo biblioteca estándar (y `psql` para PostgreSQL), para que funcione igual en el portátil y en
un notebook de Databricks. La prueba de Document Intelligence usa un plano sintético de
`examples/documents`, nunca un documento de TR.

Variables (las que falten se saltan con aviso):

    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
    AZURE_OPENAI_DEPLOYMENT            chat; sin ella se listan los despliegues
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT  opcional
    AZURE_OPENAI_API_VERSION           por defecto 2024-10-21
    AZURE_ANTHROPIC_ENDPOINT, AZURE_ANTHROPIC_API_KEY, AZURE_ANTHROPIC_MODEL  (Claude en Foundry)
    AZURE_AI_SERVICES_ENDPOINT, AZURE_AI_SERVICES_KEY     (multi-service: Document Intelligence)
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY
    PGHOST, PGUSER, PGDATABASE, PGPASSWORD (o token de `az account get-access-token`)
    AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_SAS                 (ADLS Gen2, opcional)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PDF_SINTETICO = RAIZ / "examples" / "documents" / "GAD_V-101_revA.pdf"
API_OPENAI = "2024-10-21"
API_LAYOUT = "2024-11-30"
API_SEARCH = "2024-07-01"

# Líneas inventadas con la forma de una hoja de datos: la prueba no envía nada de TR.
LINEAS_SINTETICAS = (
    "ITEM V-101 SERVICE SEPARADOR DE PRUEBA",
    "DESIGN PRESSURE (barg): 12,5",
    "INSIDE DIAMETER (mm): 2400",
    "LENGTH T.L. TO T.L. (mm): 7800",
    'N1 1 6" INLET 150# WN-RF',
)
ESQUEMA_CAMPO = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ruta", "valor", "unidad", "linea"],
    "properties": {
        "ruta": {"type": "string", "enum": ["diameter", "length", "design_pressure"]},
        "valor": {"type": ["number", "null"]},
        "unidad": {"type": "string"},
        "linea": {"type": "integer"},
    },
}


class Falta(Exception):
    """No hay datos en .env para este servicio."""


def cargar_env(ruta: Path) -> None:
    """Lee KEY=valor sin pisar variables ya definidas en el entorno."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valor = valor.strip().strip('"').strip("'")
        if valor:
            os.environ.setdefault(clave.strip(), valor)


def var(*nombres: str) -> list[str]:
    faltan = [n for n in nombres if not os.environ.get(n)]
    if faltan:
        raise Falta("faltan " + ", ".join(faltan))
    return [os.environ[n] for n in nombres]


def pedir(metodo: str, url: str, cabeceras: dict, cuerpo: dict | None = None, timeout=60):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
    if datos is not None:
        peticion.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            texto = respuesta.read().decode("utf-8") or "{}"
            return respuesta.status, dict(respuesta.headers), json.loads(texto)
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detalle}") from None


def base(url: str) -> str:
    return url.rstrip("/")


def probar_openai() -> str:
    endpoint, clave = var("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY")
    version = os.environ.get("AZURE_OPENAI_API_VERSION", API_OPENAI)
    cab = {"api-key": clave}
    despliegue = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    if not despliegue:
        # Lista de despliegues del plano de datos (API antigua, sigue respondiendo con clave).
        _, _, datos = pedir(
            "GET", f"{base(endpoint)}/openai/deployments?api-version=2022-12-01", cab
        )
        nombres = [f"{d['id']} ({d.get('model')})" for d in datos.get("data", [])]
        raise Falta("define AZURE_OPENAI_DEPLOYMENT; despliegues: " + ", ".join(nombres))
    url = f"{base(endpoint)}/openai/deployments/{despliegue}/chat/completions?api-version={version}"
    lineas = "\n".join(f"{i}: {texto}" for i, texto in enumerate(LINEAS_SINTETICAS))
    cuerpo = {
        "messages": [
            {
                "role": "system",
                "content": "Extrae el dato pedido de las líneas numeradas. Cita la línea de la que "
                "sale el valor. Si no aparece, valor null.",
            },
            {"role": "user", "content": f"Dato: diámetro interior.\n{lineas}"},
        ],
        # json_schema estricto: el canal de texto (L4) necesita que el modelo respete el contrato,
        # no solo que devuelva JSON válido como json_object.
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "campo_citado", "strict": True, "schema": ESQUEMA_CAMPO},
        },
        "max_completion_tokens": 200,
        "temperature": 0,
    }
    try:
        _, _, datos = pedir("POST", url, cab, cuerpo)
    except RuntimeError as exc:
        if "temperature" not in str(exc):
            raise
        cuerpo.pop(
            "temperature"
        )  # los modelos de razonamiento solo admiten la temperatura por defecto
        _, _, datos = pedir("POST", url, cab, cuerpo)
    uso = datos.get("usage", {})
    respuesta = json.loads(datos["choices"][0]["message"]["content"])
    linea = respuesta.get("linea")
    citada = (
        LINEAS_SINTETICAS[linea]
        if isinstance(linea, int) and 0 <= linea < len(LINEAS_SINTETICAS)
        else ""
    )
    if respuesta.get("ruta") != "diameter" or respuesta.get("valor") != 2400:
        raise RuntimeError(f"respuesta incorrecta con json_schema: {respuesta}")
    if "2400" not in citada:
        raise RuntimeError(f"la línea citada no contiene el valor: {respuesta}")
    salida = (
        f"chat {despliegue} (modelo {datos.get('model')}) con json_schema estricto: "
        f"{respuesta}; tokens {uso.get('prompt_tokens')}+{uso.get('completion_tokens')}"
    )
    embedding = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    if embedding:
        url = f"{base(endpoint)}/openai/deployments/{embedding}/embeddings?api-version={version}"
        _, _, datos = pedir("POST", url, cab, {"input": 'boquilla N1 6" 150#'})
        salida += f"; embeddings {embedding}: dim {len(datos['data'][0]['embedding'])}"
    return salida


def probar_layout() -> str:
    endpoint, clave = var("AZURE_AI_SERVICES_ENDPOINT", "AZURE_AI_SERVICES_KEY")
    url = (
        f"{base(endpoint)}/documentintelligence/documentModels/prebuilt-layout:analyze"
        f"?api-version={API_LAYOUT}"
    )
    cab = {"Ocp-Apim-Subscription-Key": clave}
    pdf = base64.b64encode(PDF_SINTETICO.read_bytes()).decode("ascii")
    _, cabeceras, _ = pedir("POST", url, cab, {"base64Source": pdf})
    operacion = cabeceras.get("Operation-Location") or cabeceras.get("operation-location")
    if not operacion:
        raise RuntimeError("sin Operation-Location en la respuesta")
    for _ in range(60):
        time.sleep(1)
        _, _, datos = pedir("GET", operacion, cab)
        if datos.get("status") in ("succeeded", "failed"):
            break
    if datos.get("status") != "succeeded":
        raise RuntimeError(f"análisis {datos.get('status')}: {datos.get('error')}")
    resultado = datos["analyzeResult"]
    paginas = resultado.get("pages", [])
    tablas = resultado.get("tables", [])
    lineas = sum(len(p.get("lines", [])) for p in paginas)
    celdas = sum(len(t.get("cells", [])) for t in tablas)
    return (
        f"layout sobre {PDF_SINTETICO.name} (sintético): {len(paginas)} página(s), "
        f"{lineas} líneas, {len(tablas)} tablas, {celdas} celdas"
    )


def probar_search() -> str:
    endpoint, clave = var("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_KEY")
    cab = {"api-key": clave}
    _, _, datos = pedir("GET", f"{base(endpoint)}/servicestats?api-version={API_SEARCH}", cab)
    contadores = datos.get("counters", {})
    indices = contadores.get("indexesCount", {})
    _, _, lista = pedir(
        "GET", f"{base(endpoint)}/indexes?api-version={API_SEARCH}&$select=name", cab
    )
    nombres = [i["name"] for i in lista.get("value", [])]
    return f"search: índices {indices.get('usage')}/{indices.get('quota')} {nombres}"


def probar_postgres() -> str:
    (host,) = var("PGHOST")
    if not shutil.which("psql"):
        raise Falta("no está psql en el PATH")
    entorno = dict(os.environ)
    entorno.setdefault("PGSSLMODE", "require")
    if not entorno.get("PGPASSWORD"):
        # Autenticación de Entra ID: el token de Azure CLI hace de contraseña.
        az = shutil.which("az")
        if not az:
            raise Falta("falta PGPASSWORD o Azure CLI (az login) para pedir el token")
        token = subprocess.run(
            [
                az,
                "account",
                "get-access-token",
                "--resource-type",
                "oss-rdbms",
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        entorno["PGPASSWORD"] = token
    proceso = subprocess.run(
        ["psql", "-X", "-A", "-t", "-c", "select current_user, version()"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=30,
    )
    if proceso.returncode:
        raise RuntimeError(proceso.stderr.strip()[:300])
    return f"postgres {host}: {proceso.stdout.strip()[:120]}"


def probar_adls() -> str:
    cuenta, sas = var("AZURE_STORAGE_ACCOUNT", "AZURE_STORAGE_SAS")
    url = f"https://{cuenta}.dfs.core.windows.net/?resource=account&{sas.lstrip('?')}"
    _, _, datos = pedir("GET", url, {"x-ms-version": "2023-11-03"})
    nombres = [f["name"] for f in datos.get("filesystems", [])]
    return f"adls {cuenta}: sistemas de archivos {nombres}"


def probar_anthropic() -> str:
    """Claude en Azure AI Foundry (API de mensajes de Anthropic) con las líneas sintéticas."""
    endpoint, clave = var("AZURE_ANTHROPIC_ENDPOINT", "AZURE_ANTHROPIC_API_KEY")
    modelo = os.environ.get("AZURE_ANTHROPIC_MODEL", "claude-sonnet-5-5")
    url = base(endpoint)
    if not url.endswith("/v1/messages"):
        url += "/v1/messages"
    cab = {"x-api-key": clave, "anthropic-version": "2023-06-01"}
    lineas = "\n".join(f"{i}: {texto}" for i, texto in enumerate(LINEAS_SINTETICAS))
    cuerpo = {
        "model": modelo,
        "max_tokens": 300,
        "system": "Extrae el dato pedido de las líneas numeradas y cita la línea de la que sale. "
        'Responde solo con JSON: {"ruta": "diameter", "valor": número o null, '
        '"unidad": texto, "linea": entero}.',
        "messages": [{"role": "user", "content": f"Dato: diámetro interior.\n{lineas}"}],
    }
    _, _, datos = pedir("POST", url, cab, cuerpo)
    texto = next((b["text"] for b in datos.get("content", []) if b.get("type") == "text"), "")
    inicio, fin = texto.find("{"), texto.rfind("}")
    respuesta = json.loads(texto[inicio : fin + 1]) if inicio >= 0 else {}
    linea = respuesta.get("linea")
    citada = (
        LINEAS_SINTETICAS[linea]
        if isinstance(linea, int) and 0 <= linea < len(LINEAS_SINTETICAS)
        else ""
    )
    if respuesta.get("valor") != 2400 or "2400" not in citada:
        raise RuntimeError(f"respuesta incorrecta: {respuesta}")
    uso = datos.get("usage", {})
    return (
        f"claude {datos.get('model', modelo)}: {respuesta}; "
        f"tokens {uso.get('input_tokens')}+{uso.get('output_tokens')}"
    )


PRUEBAS = {
    "openai": probar_openai,
    "anthropic": probar_anthropic,
    "layout": probar_layout,
    "search": probar_search,
    "postgres": probar_postgres,
    "adls": probar_adls,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=RAIZ / ".env")
    parser.add_argument("--solo", choices=sorted(PRUEBAS), action="append")
    parser.add_argument(
        "--permitir-saltos",
        action="store_true",
        help="devolver 0 aunque falten credenciales de algún servicio",
    )
    args = parser.parse_args()
    cargar_env(args.env)
    fallos = saltos = 0
    for nombre in args.solo or PRUEBAS:
        inicio = time.perf_counter()
        try:
            detalle = PRUEBAS[nombre]()
            estado = "OK   "
        except Falta as exc:
            detalle, estado = str(exc), "SALTA"
            saltos += 1
        except Exception as exc:  # noqa: BLE001 — cada servicio informa y se sigue con el resto
            detalle, estado = f"{type(exc).__name__}: {exc}", "FALLA"
            fallos += 1
        print(f"{estado} {nombre:9} {time.perf_counter() - inicio:5.1f} s  {detalle}")
    # 1: algún servicio falla. 2: alguno no se probó. Solo 0 si todo lo pedido respondió bien.
    if fallos:
        return 1
    return 2 if saltos and not args.permitir_saltos else 0


if __name__ == "__main__":
    sys.exit(main())
