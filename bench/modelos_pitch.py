"""Compara los cinco despliegues con entradas que genera el propio banco."""

import argparse
import base64
import hashlib
import io
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont

from trazia.llm.claude_azure import VERSION_API, AzureClaudeProvider
from trazia.vision.base import VisionError, VisionUnavailable
from trazia.vision.providers import AzureOpenAIProvider, _json_from_text, _post

MODELS = {
    "gpt-6-luna": ("GPT-6 Luna", 0.10, 0.50),
    "gpt-6.1-sol": ("GPT-6.1 Sol", 2.00, 10.00),
    "claude-haiku-5-5": ("Haiku 5.5", 0.10, 0.50),
    "claude-sonnet-5-5": ("Sonnet 5.5", 2.00, 10.00),
    "claude-opus-5-5": ("Opus 5.5", 4.00, 20.00),
}
PRICE_SOURCES = [
    "https://developers.openai.com/api/docs/pricing",
    "https://platform.claude.com/docs/en/about-claude/pricing",
]
SCHEMA = (
    'Devuelve exclusivamente JSON con forma {"fields":{"id":{"value":número,"unit":"unidad"}}}. '
    'Si el campo no aparece o no se puede leer, usa {"value":null,"unit":null}. '
    "Usa mm para dimensiones, in para NPS, ° para ángulos y bar para presión. "
    "Conserva el signo y la referencia indicada. Ignora cotas tachadas o asignadas a otra pieza. "
)


@dataclass(frozen=True)
class Case:
    identity: str
    task: str
    prompt: str
    expected: dict
    png: bytes | None = None


def fixtures():
    rng = random.Random(20261126)
    for i in range(20):
        diameter = rng.randrange(1300, 2700, 50)
        span = rng.randrange(4000, 8900, 50)
        level = rng.randrange(550, 2500, 25)
        projection = rng.randrange(150, 550, 25)
        missing = i % 5 == 0
        label = ("N1", "M2", "A3", "D4")[i % 4]
        image = Image.new("RGB", (950, 580), "white")
        draw = ImageDraw.Draw(image)
        title = ImageFont.load_default(size=27)
        font = ImageFont.load_default(size=23)
        ink = "#182a37"
        draw.rectangle((14, 14, 935, 565), outline=ink, width=3)
        draw.text((36, 37), f"GA DE ENSAYO / EQUIPO DEMO-{100 + i} / REV B", fill=ink, font=title)
        draw.rounded_rectangle((325, 120, 565, 475), radius=65, outline=ink, width=4)
        draw.line((445, 95, 445, 504), fill="#a0a5ac", width=2)
        draw.line((565, 222, 650, 222), fill=ink, width=5)
        draw.line((650, 201, 650, 245), fill=ink, width=4)
        draw.text((682, 200), label, fill=ink, font=title)
        draw.line((327, 117, 565, 117), fill="#456d82", width=2)
        dia_text = f"Ø{diameter} I.D." if i % 2 else f"DI {diameter}"
        draw.text((340, 82), dia_text, fill=ink, font=font)
        draw.text((340, 285), f"Ø{diameter + 50} O.D.", fill="#68717a", font=font)
        draw.line((272, 190, 272, 410), fill="#456d82", width=2)
        draw.text((38, 276), f"{span} T.L.–T.L.", fill=ink, font=font)
        draw.text((681, 251), f"EL.+{level}", fill=ink, font=font)
        draw.text((681, 292), f"EL.+{level - 170} (N9)", fill="#68717a", font=font)
        if not missing:
            text = f"PROJ. {projection}" if i % 2 else f"SALIENTE {projection}"
            draw.text((674, 344), text, fill=ink, font=font)
            draw.line((568, 358, 649, 358), fill="#456d82", width=2)
        draw.text((42, 520), "COTAS EN mm · RECORTE DE PRUEBA SINTÉTICA", fill=ink, font=font)
        out = io.BytesIO()
        image.save(out, format="PNG")
        prompt = (
            SCHEMA + f"Extrae del recorte solo estos campos: di (diámetro interior), "
            f"tl (virola entre tangentes), el (elevación de {label}), "
            f"proj (proyección de {label})."
        )
        yield Case(
            f"ga-{i + 1:02}",
            "vision",
            prompt,
            {
                "di": (diameter, "mm"),
                "tl": (span, "mm"),
                "el": (level, "mm"),
                "proj": None if missing else (projection, "mm"),
            },
            out.getvalue(),
        )

    definitions = [
        ("DI={n} mm; OLD {old} mm superseded", "di", "di", "mm", 1, 1),
        ("{n} (T.L. To T.L.) [mm]; O/A {old}", "tl", "tl", "mm", 1, 1),
        ("PL.+{old}; boquilla T5 EL.-{n} mm", "el de T5", "el", "mm", -1, 1),
        ("TAG M3 ON AXIS {n}°; M8 {old}°", "azimut de M3", "az", "°", 1, 1),
        ("P. TEST {old} bar / P. DESIGN {n} bar", "presión de diseño", "pressure", "bar", 1, 1),
        ("N8: NPS {n}\u2033 300# RF; OD {old} mm", "NPS de N8", "nps", "in", 1, 1),
        ("DIÁM. INT. {n} cm / EXTERIOR {old} mm", "di", "di", "mm", 1, 10),
        ("TL–TL {n} m; OA {old} m", "tl", "tl", "mm", 1, 1000),
    ]
    for i in range(40):
        template, name, key, unit, sign, factor = definitions[i % len(definitions)]
        value = (
            rng.randrange(4, 12)
            if unit in {"in", "bar"} or factor == 1000
            else rng.randrange(20, 680)
        )
        if key == "az":
            value %= 360
        fragment = template.format(n=value, old=(value + 4) % 360 if key == "az" else value + 4)
        prompt = SCHEMA + f"Normaliza solo el campo {name} con ID {key}. Fragmento: «{fragment}»."
        yield Case(f"txt-{i + 1:02}", "texto", prompt, {key: (value * sign * factor, unit)})


def client(model):
    claude = model.startswith("claude-")
    provider = AzureClaudeProvider(model) if claude else AzureOpenAIProvider(deployment=model)
    host = urlsplit(provider.url).hostname
    if not host or not host.endswith(
        (".services.ai.azure.com", ".cognitiveservices.azure.com", ".openai.azure.com")
    ):
        raise ValueError("La URL del banco debe apuntar a un recurso de Azure configurado.")
    return provider, claude


def query(provider, claude, case, *, max_tokens=2048):
    content = [{"type": "text", "text": case.prompt}]
    if case.png:
        encoded = base64.b64encode(case.png).decode("ascii")
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": encoded},
            }
            if claude
            else {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
        )
    payload = {"messages": [{"role": "user", "content": content}]}
    if claude:
        payload.update(model=provider.model, max_tokens=max_tokens)
        headers = {"x-api-key": provider.key, "anthropic-version": VERSION_API}
    else:
        payload["max_completion_tokens"] = max_tokens
        headers = {"api-key": provider.key}
    response = _post(provider.url, payload, headers, timeout=50)
    usage = response.get("usage") or {}
    if claude:
        text = "".join(
            block["text"] for block in response.get("content", []) if block["type"] == "text"
        )
        tokens = (usage.get("input_tokens"), usage.get("output_tokens"))
    else:
        text = (response.get("choices") or [{}])[0].get("message", {}).get("content")
        tokens = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
    try:
        data = _json_from_text(text)
    except (ValueError, TypeError, AttributeError):
        data = {}
    return data, tokens


def evaluate(data, expected):
    fields = data.get("fields")
    fields = fields if isinstance(fields, dict) else {}
    counts = dict(correct=0, wrong=0, omitted=0, absent=0, abstained=0)
    for key, truth in expected.items():
        answer = fields.get(key)
        answer = answer if isinstance(answer, dict) else {}
        value, unit = answer.get("value"), answer.get("unit")
        if truth is None:
            counts["absent"] += 1
            counts["abstained"] += key in fields and value is None and not unit
        elif value is None:
            counts["omitted"] += 1
        elif type(value) in (int, float) and value == truth[0] and unit == truth[1]:
            counts["correct"] += 1
        else:
            counts["wrong"] += 1
    return counts


def run_case(model, pair, case):
    start = time.perf_counter()
    error = None
    try:
        data, tokens = query(*pair, case)
    except (VisionError, VisionUnavailable, ValueError) as exc:
        match = re.search(r"HTTP (\d{3})", str(exc))
        error = f"HTTP {match[1]}" if match else type(exc).__name__
        data, tokens = {}, (None, None)
    _, price_in, price_out = MODELS[model]
    cost = (tokens[0] * price_in + tokens[1] * price_out) / 1e6 if None not in tokens else None
    return {
        "model": model,
        "case": case.identity,
        "task": case.task,
        "error": error,
        "seconds": round(time.perf_counter() - start, 4),
        "usd": cost,
        "tokens_in": tokens[0],
        "tokens_out": tokens[1],
        **evaluate(data, case.expected),
    }


def aggregate(rows, cases):
    tasks = {}
    for task, selected in (("vision", "gpt-6.1-sol"), ("texto", "gpt-6-luna")):
        points = []
        for model, (name, _, _) in MODELS.items():
            group = [item for item in rows if item["model"] == model and item["task"] == task]
            successes = [item for item in group if not item["error"]]
            fields = sum(
                sum(item[key] for key in ("correct", "wrong", "omitted")) for item in group
            )
            costs = [item["usd"] for item in successes if item["usd"] is not None]
            points.append(
                {
                    "id": model,
                    "name": name,
                    "correct": sum(item["correct"] for item in group),
                    "fields": fields,
                    "wrong": sum(item["wrong"] for item in group),
                    "abstained": sum(item["abstained"] for item in group),
                    "absent": sum(item["absent"] for item in group),
                    "failures": len(group) - len(successes),
                    "calls": len(group),
                    "seconds": median(item["seconds"] for item in successes) if successes else None,
                    "usd": mean(costs) if costs and len(costs) == len(group) else None,
                }
            )
        tasks[task] = {"selected": selected, "points": points}
    signature = hashlib.sha256()
    for case in cases:
        signature.update(case.prompt.encode())
        signature.update(json.dumps(case.expected, sort_keys=True).encode())
        signature.update(case.png or b"")
    return {
        "dataset": "sintético",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "sha256": signature.hexdigest(),
        "priceSources": PRICE_SOURCES,
        "tasks": tasks,
        "projection": savings(rows),
    }


def savings(rows):
    # El lote de cuatro revisiones registró 86 llamadas complejas y cero respaldos. Se
    # escala ese tráfico a 20 revisiones. El intervalo solo propaga variación entre recortes.
    costs = {}
    for item in rows:
        if item["task"] == "vision" and item["usd"] is not None:
            costs.setdefault(item["model"], {})[item["case"]] = item["usd"]
    sol = costs.get("gpt-6.1-sol", {})
    opus = costs.get("claude-opus-5-5", {})
    if len(sol) != 20 or sol.keys() != opus.keys():
        return None
    pairs = [(sol[key], opus[key]) for key in sorted(sol)]
    average_sol, average_opus = map(mean, zip(*pairs))
    rng = random.Random(20261126)
    ratios = []
    for _ in range(3000):
        sample_sol, sample_opus = map(sum, zip(*rng.choices(pairs, k=len(pairs))))
        ratios.append(1 - sample_sol / sample_opus)
    ratios.sort()
    calls = 86 * 20 // 4
    return {
        "calls": calls,
        "revisions": 20,
        "measuredCalls": 86,
        "measuredRevisions": 4,
        "central": 1 - average_sol / average_opus,
        "optimistic": ratios[2849],
        "lower": ratios[150],
        "solUsd": average_sol * calls,
        "opusUsd": average_opus * calls,
    }


def load_azure_environment(path):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith(("AZURE_OPENAI_", "AZURE_ANTHROPIC_")) and value.strip():
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--salida", type=Path, default=Path("generated/bench/modelos-pitch"))
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--reintentar", action="store_true", help="Repite solo los fallos de transporte."
    )
    args = parser.parse_args()
    load_azure_environment(args.env)
    clients = {model: client(model) for model in MODELS}
    cases = list(fixtures())
    if args.smoke:
        cases = [cases[0], cases[20]]
    job = [(model, case) for case in cases for model in MODELS]
    random.Random(20261126).shuffle(job)
    args.salida.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.reintentar:
        previous = json.loads((args.salida / "llamadas.json").read_text(encoding="utf-8"))
        indexed = {(row["model"], row["case"]): row for row in previous}
        rows = [row for row in previous if not row["error"]]
        job = [(model, case) for model, case in job if indexed[(model, case.identity)]["error"]]
    with ThreadPoolExecutor(max_workers=5) as executor:
        pending = [executor.submit(run_case, model, clients[model], case) for model, case in job]
        for number, done in enumerate(as_completed(pending), start=1):
            row = done.result()
            if args.reintentar:
                previous_row = indexed[(row["model"], row["case"])]
                row["previous_errors"] = [
                    *previous_row.get("previous_errors", []),
                    previous_row["error"],
                ]
            rows.append(row)
            if row["error"] or args.smoke:
                print(row["model"], row["case"], row["error"] or "OK", flush=True)
            if number % 20 == 0:
                print(f"{number}/{len(job)}", flush=True)
    result = aggregate(rows, cases)
    for filename, data in (("llamadas.json", rows), ("benchmark.json", result)):
        (args.salida / filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{len(rows)} llamadas, {sum(bool(row['error']) for row in rows)} errores", flush=True)


if __name__ == "__main__":
    main()
