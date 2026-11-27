"""Agrupa documentos del reto por equipo y revisión y escribe el lote local.

Las hojas sin revisión acompañan a todas las de su equipo. Cada revisión produce
eventos de ingesta y lectura. Cuando hay datos suficientes, produce el contrato y
el IFC4 DRAFT. Los resúmenes JSON y CSV recogen los estados de todas las revisiones.
"""

import csv
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from pathlib import Path

from .ingest import IMAGE_SUFFIXES, dataset_filename

DATASETS = ("real", "synthetic")
SUFFIXES = (".pdf", ".xlsx", *IMAGE_SUFFIXES)
ORDEN_TIPO = {"GA": 0, "HDM": 1, "VESOR": 2, "ESTRUCTURA": 3}
CACHES = {
    "TRAZIA_OCR_CACHE": "ocr",
    "TRAZIA_VISION_CACHE": "vision",
}


@dataclass
class Fila:
    tag: str
    revision: str
    documentos: list[str]
    estado: str  # "ok", "faltan_datos", "tipologia_no_soportada" o "error"
    error: str | None = None
    familia: str | None = None
    lod: int | None = None
    boquillas: int | None = None
    campos: int | None = None
    pendientes: int | None = None
    avisos: int = 0
    cambios: int | None = None
    segundos: float = 0.0
    carpeta: str = ""
    # Documentos que no se pudieron leer aunque la revisión siguiera adelante con el resto.
    # Sin esta columna el fallo solo quedaba en eventos.json y el lote decía «ok».
    documentos_con_error: list[str] = field(default_factory=list)
    avisos_documentos: list[str] = field(default_factory=list)


@dataclass
class Documento:
    path: Path
    kind: str
    tag: str
    revision: str | None
    sheet: str | None = None
    document_id: str = field(init=False)
    alternativo: bool = False
    alertas: list[str] = field(default_factory=list)

    def __post_init__(self):
        parts = [self.kind, identificador(self.tag)]
        if self.sheet and not self.tag.endswith(f"-{self.sheet}"):
            parts.append(self.sheet)
        self.document_id = "-".join(parts)

    def entrada(self):
        from .pipeline import InputDocument

        return InputDocument(
            self.path.name,
            self.path.read_bytes(),
            self.document_id,
            tag_hint=self.tag if self.alternativo else None,
        )


def identificador(texto: str) -> str:
    """Los ids del contrato solo admiten letras, cifras, `_` y `-`."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", texto).strip("-") or "sin-tag"


def configurar_cache(trabajo: Path) -> dict[str, str]:
    """Fija las cachés en `trabajo/cache/...` sin pisar las variables que ya estén definidas."""
    fijadas = {}
    for variable, carpeta in CACHES.items():
        if not os.environ.get(variable):
            os.environ[variable] = str(Path(trabajo) / "cache" / carpeta)
        fijadas[variable] = os.environ[variable]
    if not os.environ.get("TRAZIA_REGISTRO_ENVIOS"):
        os.environ["TRAZIA_REGISTRO_ENVIOS"] = str(Path(trabajo) / "registro_envios.jsonl")
    fijadas["TRAZIA_REGISTRO_ENVIOS"] = os.environ["TRAZIA_REGISTRO_ENVIOS"]
    return fijadas


def _orden(revision: str):
    """Revisiones en orden natural: 1 < 2 < 10 y A < B."""
    return [
        (0, int(t)) if t.isdigit() else (1, t.upper()) for t in re.split(r"(\d+)", revision) if t
    ]


def agrupar(
    entrada: Path, ignorados: list[dict] | None = None
) -> dict[str, dict[str, list[Documento]]]:
    """Agrupa por equipo; el nombre convencional conserva la precedencia histórica."""
    from .ingest import image_to_pdf, ingest_bytes
    from .lectura.clasificar import classify

    entrada = Path(entrada)
    encontrados: dict[str, list[Documento]] = defaultdict(list)

    def ignorar(path, motivo):
        if ignorados is not None:
            ignorados.append({"archivo": path.relative_to(entrada).as_posix(), "motivo": motivo})

    for path in sorted(entrada.rglob("*"), key=lambda p: _orden(p.as_posix())):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUFFIXES:
            ignorar(path, "formato fuera de los documentos de entrada")
            continue
        if info := dataset_filename(path.name):
            doc = Documento(path, info.kind, info.catalogue_tag, info.revision, info.sheet)
            encontrados[doc.tag].append(doc)
            continue
        try:
            data = path.read_bytes()
            if path.suffix.lower() in IMAGE_SUFFIXES:
                data = image_to_pdf(data)
                name = path.with_suffix(".pdf").name
            else:
                name = path.name
            bundle = ingest_bytes(data, name, "INSPECCION-LOTE", "1")
        except Exception as error:  # un original dañado tampoco debe desaparecer del resumen
            ignorar(path, f"no se pudo inspeccionar ({type(error).__name__})")
            continue
        carpeta = path.parent.name if path.parent != entrada else None
        meta = classify(bundle, tag_hint=carpeta, data=data)
        if meta.kind is None:
            sufijo = "; plano sin texto: necesita OCR" if bundle.sparse_pages else ""
            ignorar(path, meta.reason + sufijo)
            continue
        tag = carpeta or meta.tag
        if not tag:
            ignorar(path, "falta el tag del cajetín o una carpeta de equipo")
            continue
        doc = Documento(path, meta.kind, tag, meta.revision, alternativo=True)
        if meta.revision_source:
            doc.alertas.append(
                f"{path.name}: revisión {meta.revision} del cajetín (pág. "
                f"{meta.revision_source.source.page})."
            )
        encontrados[doc.tag].append(doc)
    _repartir_comunes_por_hoja(encontrados)
    grupos = {}
    for tag in sorted(encontrados):
        docs = encontrados[tag]
        _revisiones_por_orden(docs)
        revisiones = sorted({d.revision for d in docs if d.revision}, key=_orden)
        comunes = [d for d in docs if d.revision is None]
        if not revisiones:
            grupos[tag] = {"1": comunes}
            continue
        grupos[tag] = {r: [d for d in docs if d.revision == r] + comunes for r in revisiones}
    for revisiones in grupos.values():
        for docs in revisiones.values():
            docs.sort(key=lambda d: (ORDEN_TIPO.get(d.kind, 9), d.path.name))
    return grupos


def _repartir_comunes_por_hoja(encontrados: dict[str, list[Documento]]) -> None:
    """Una hoja de datos `HDM_BOMBA` acompaña a cada equipo `BOMBA-GA<n>`.

    Los GA mecánicos llevan la hoja en el tag porque cada uno es otra máquina. Lo que solo
    nombra el prefijo, sin ningún GA propio, se copia a cada una con un aviso.
    """
    hojas: dict[str, list[str]] = defaultdict(list)
    for tag, docs in encontrados.items():
        for doc in docs:
            if doc.sheet and tag.upper().endswith(f"-{doc.sheet.upper()}"):
                prefijo = tag[: -len(doc.sheet) - 1].upper()
                if tag not in hojas[prefijo]:
                    hojas[prefijo].append(tag)
    for tag in list(encontrados):
        equipos = hojas.get(tag.upper())
        if not equipos or any(doc.kind == "GA" for doc in encontrados[tag]):
            continue
        for doc in encontrados.pop(tag):
            for equipo in equipos:
                copia = replace(doc, tag=equipo, alertas=list(doc.alertas))
                copia.document_id = doc.document_id  # el mismo original, el mismo ID
                copia.alertas.append(f"{doc.path.name}: común a {', '.join(sorted(equipos))}.")
                encontrados[equipo].append(copia)


def _revisiones_por_orden(docs):
    planos = [doc for doc in docs if doc.kind == "GA"]
    repetidas = Counter(doc.revision for doc in planos if doc.revision)
    for doc in planos:
        if doc.alternativo and doc.revision and repetidas[doc.revision] > 1:
            doc.alertas.append(f"{doc.path.name}: REV {doc.revision} repetida en varios GA.")
            doc.revision = None
    usadas = {doc.revision for doc in planos if doc.revision}
    for i, doc in enumerate(planos, 1):
        if doc.alternativo and doc.revision is None:
            numero = i
            while str(numero) in usadas:
                numero += 1
            usadas.add(str(numero))
            doc.revision = str(numero)
            doc.alertas.append(
                f"{doc.path.name}: revisión {numero} asignada por orden (sin REV inequívoca)."
            )
    hojas = [doc for doc in docs if doc.kind == "HDM"]
    fechas = sorted(usadas, key=_orden)
    for doc in docs:
        if doc.alternativo and doc.kind in ("VESOR", "ESTRUCTURA") and doc.revision and fechas:
            # Los planos auxiliares tienen su propia numeración y se comparten en el dataset.
            doc.alertas.append(
                f"{doc.path.name}: revisión auxiliar {doc.revision}; se usa en todo el equipo."
            )
            doc.revision = None
    if len(hojas) == 1 and hojas[0].alternativo and len(fechas) > 1:
        hoja = hojas[0]
        hoja.alertas.append(
            f"{hoja.path.name}: única hoja de datos; común a las revisiones del equipo."
        )
        hoja.revision = None
    elif len(hojas) > 1:
        hdm_repetidas = Counter(h.revision for h in hojas if h.revision)
        for hoja in hojas:
            if hoja.alternativo and hoja.revision and hdm_repetidas[hoja.revision] > 1:
                hoja.alertas.append(f"{hoja.path.name}: REV {hoja.revision} repetida en las HDM.")
                hoja.revision = None
        ocupadas = {hoja.revision for hoja in hojas if hoja.revision in usadas}
        libres = iter([rev for rev in fechas if rev not in ocupadas])
        for hoja in hojas:
            if hoja.alternativo and hoja.revision not in usadas:
                rev = next(libres, None)
                if rev:
                    hoja.revision = rev
                    hoja.alertas.append(
                        f"{hoja.path.name}: asociada por orden a la revisión {rev} del GA."
                    )
                else:
                    hoja.alertas.append(
                        f"{hoja.path.name}: sin GA equivalente; se conserva su revisión."
                    )


def _escribir(path: Path, contenido: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contenido, bytes):
        path.write_bytes(contenido)
    else:
        path.write_text(contenido, encoding="utf-8")


def _suponer_azimuts(tag, hechos, salida, *, proyecto, proveedores, dataset):
    """Rehace las revisiones sin ningún azimut con el de la revisión siguiente, como supuesto.

    La planta de algunas rev1 dice «TO BE DEFINED BY CLIENT». Sin azimut la boquilla no se
    coloca. La revisión siguiente sí lo fija: se reutiliza la lectura ya hecha y solo se
    vuelve a montar el modelo.
    """
    from .extraction import Candidate
    from .families.change_detection import preserve_nozzle_identity
    from .ifc import build_ifc, validate_ifc
    from .lectura.cambios import comparar_candidatos, completar
    from .lectura.orientacion import azimuts_supuestos
    from .model import Revision, fields
    from .pipeline import process
    from .revisions import compare

    def cambios_entre(izquierda, derecha):
        if izquierda["revision"] is None or derecha["revision"] is None:
            return
        informe = compare(izquierda["revision"], derecha["revision"])
        if izquierda["candidatos"] and derecha["candidatos"]:
            informe = completar(
                informe, comparar_candidatos(izquierda["candidatos"], derecha["candidatos"])
            )
        nombre = f"cambios_rev{izquierda['etiqueta']}_rev{derecha['etiqueta']}.json"
        _escribir(
            Path(salida) / tag / nombre,
            json.dumps(informe, ensure_ascii=False, indent=2, default=str),
        )
        derecha["fila"].cambios = len(informe.get("changes", []))

    for indice, hecho in enumerate(hechos[:-1]):
        if not hecho["candidatos"]:
            continue
        try:
            leidos = [Candidate.model_validate(c) for c in hecho["candidatos"]]
        except Exception:
            continue
        extra = azimuts_supuestos(leidos, hechos[indice + 1]["candidatos"])
        if not extra:
            continue
        anterior = hechos[indice - 1]["revision"] if indice else None
        docs = hecho["docs"]

        def reader(_bundles, **_kwargs):
            return [*leidos, *extra]

        try:
            entradas = [doc.entrada() for doc in docs]
            result = process(
                entradas,
                project_id=proyecto,
                equipment_id=identificador(tag).lower(),
                revision=hecho["etiqueta"],
                previous=anterior,
                providers=proveedores,
                dataset=dataset,
                reader=reader,
            )
        except Exception:
            continue
        if result.error or result.revision is None:
            continue
        revision = Revision.model_validate_json(result.revision.model_dump_json())
        revision.approval = None
        if anterior is not None:
            revision = preserve_nozzle_identity(anterior, revision)
        revision.run = result.run
        try:
            modelo = build_ifc(revision, draft=True)
            problemas = validate_ifc(modelo)
        except Exception:
            continue
        if problemas:
            continue
        carpeta = Path(hecho["fila"].carpeta)
        _escribir(carpeta / "revision.json", revision.model_dump_json(indent=2))
        _escribir(carpeta / "modelo.ifc", modelo.to_string())
        equipo = revision.equipment
        fila = hecho["fila"]
        fila.estado = "ok"
        fila.error = None
        fila.familia, fila.lod = equipo.kind, equipo.lod
        fila.boquillas = len(equipo.nozzles)
        campos = fields(equipo)
        fila.campos = len(campos)
        fila.pendientes = len(revision.pending_review())
        hecho["revision"] = revision
        hecho["candidatos"] = [c.model_dump(mode="json") for c in result.candidates]
        _escribir(
            carpeta / "candidatos.json",
            json.dumps(hecho["candidatos"], ensure_ascii=False, indent=2),
        )
        if indice:
            cambios_entre(hechos[indice - 1], hecho)
        cambios_entre(hecho, hechos[indice + 1])


def procesar_equipo(
    tag: str,
    revisiones: dict[str, list[Documento]],
    salida: Path,
    *,
    proyecto: str,
    proveedores: list[str] | None = None,
    dataset: str = "real",
    evidencias=None,
) -> list[Fila]:
    from .ifc import build_ifc, validate_ifc
    from .model import Revision
    from .pipeline import process
    from .revisions import compare

    reader = None
    if evidencias:
        from .lectura.evidencias import leer_con_evidencias

        reader = partial(leer_con_evidencias, evidencias=evidencias)

    filas, anterior, etiqueta_anterior = [], None, None
    leidos_anteriores, etiqueta_leida = None, None  # candidatos de la revisión anterior
    hechos = []
    for etiqueta, docs in revisiones.items():
        carpeta = Path(salida) / tag / f"rev{etiqueta}"
        nombres = [d.path.name for d in docs]
        fila = Fila(tag, etiqueta, nombres, "error", carpeta=str(carpeta))
        eventos = []
        candidatos = []
        comparada = False
        revision_ok = None
        inicio = time.perf_counter()
        try:
            entradas = [doc.entrada() for doc in docs]
            result = process(
                entradas,
                project_id=proyecto,
                equipment_id=identificador(tag).lower(),
                revision=etiqueta,
                previous=anterior,
                providers=proveedores,
                dataset=dataset,
                on_event=lambda e: eventos.append(asdict(e)),
                reader=reader,
            )
            candidatos = [c.model_dump(mode="json") for c in result.candidates]
            fila.avisos = len(result.warnings)
            if result.error or result.revision is None:
                fila.error = result.error or "Sin revisión"
                if result.unsupported_type:
                    fila.estado = "tipologia_no_soportada"
                elif result.missing_data:
                    fila.estado = "faltan_datos"
                    if not _hay_geometria(candidatos) and not _hay_tipo(candidatos):
                        # Sin cotas ni tipo no se sabe la familia: pedir «diámetro y faldón» a
                        # una bomba sería un mensaje falso. La lista de campos de recipiente
                        # se queda en eventos.json. Con el tipo leído, el error ya es el de
                        # su familia y se conserva.
                        fila.error = f"{FAMILIA_NO_RECONOCIDA} {SIN_FAMILIA}"
            else:
                revision = Revision.model_validate_json(result.revision.model_dump_json())
                revision.approval = None
                if anterior is not None:
                    from .families.change_detection import preserve_nozzle_identity

                    revision = preserve_nozzle_identity(anterior, revision)
                revision.run = result.run
                modelo = build_ifc(revision, draft=True)
                problemas = validate_ifc(modelo)
                if problemas:
                    fila.error = "IFC inválido: " + problemas[0]["message"][:300]
                else:
                    _escribir(carpeta / "revision.json", revision.model_dump_json(indent=2))
                    _escribir(carpeta / "modelo.ifc", modelo.to_string())
                    equipo = revision.equipment
                    fila.estado = "tipologia_no_soportada" if result.unsupported_type else "ok"
                    if result.unsupported_type:
                        fila.error = (
                            f"tipología no soportada: {result.unsupported_type}"
                            " · solo envolvente LOD 1"
                        )
                    fila.familia, fila.lod = equipo.kind, equipo.lod
                    fila.boquillas = len(equipo.nozzles)
                    from .model import fields

                    campos = fields(equipo)
                    fila.campos = len(campos)
                    fila.pendientes = len(revision.pending_review())
                    if anterior is not None:
                        cambios = compare(anterior, revision)
                        if leidos_anteriores and candidatos:
                            from .lectura.cambios import comparar_candidatos, completar

                            leido = comparar_candidatos(leidos_anteriores, candidatos)
                            cambios = completar(cambios, leido)
                        nombre = f"cambios_rev{etiqueta_anterior}_rev{etiqueta}.json"
                        _escribir(
                            Path(salida) / tag / nombre,
                            json.dumps(cambios, ensure_ascii=False, indent=2, default=str),
                        )
                        fila.cambios = len(cambios.get("changes", []))
                        comparada = True
                    anterior, etiqueta_anterior = revision, etiqueta
                    revision_ok = revision
            avisos = [*result.warnings, *(aviso for doc in docs for aviso in doc.alertas)]
            fila.avisos = len(avisos)
            fila.avisos_documentos = avisos
        except Exception as exc:  # un equipo roto no detiene el lote: queda en el resumen
            fila.error = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
            avisos = []
        if not comparada and candidatos and leidos_anteriores:
            if _hay_lectura(candidatos) and _hay_lectura(leidos_anteriores):
                # Sin modelo en alguna de las dos: el cambio se mide sobre lo leído por ID.
                from .lectura.cambios import comparar_candidatos

                cambios = comparar_candidatos(leidos_anteriores, candidatos)
                _escribir(
                    Path(salida) / tag / f"cambios_rev{etiqueta_leida}_rev{etiqueta}.json",
                    json.dumps(cambios, ensure_ascii=False, indent=2, default=str),
                )
                fila.cambios = len(cambios["changes"])
            else:
                # Comparar solo el tag daría «0 cambios»: falso si no se leyó nada.
                avisos.append(SIN_LECTURA.format(etiqueta_leida, etiqueta))
                fila.avisos = len(avisos)
                fila.avisos_documentos = avisos
        if candidatos:
            leidos_anteriores, etiqueta_leida = candidatos, etiqueta
        fila.documentos_con_error = _documentos_con_error(eventos, nombres)
        fila.segundos = round(time.perf_counter() - inicio, 3)
        _escribir(carpeta / "candidatos.json", json.dumps(candidatos, ensure_ascii=False, indent=2))
        _escribir(
            carpeta / "eventos.json",
            json.dumps(
                {"eventos": eventos, "avisos": avisos, "error": fila.error},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
        filas.append(fila)
        hechos.append(
            {
                "etiqueta": etiqueta,
                "docs": docs,
                "candidatos": candidatos,
                "revision": revision_ok,
                "fila": fila,
            }
        )
    _suponer_azimuts(
        tag, hechos, salida, proyecto=proyecto, proveedores=proveedores, dataset=dataset
    )
    return filas


def _uno(argumentos):
    return procesar_equipo(*argumentos[:3], **argumentos[3])


def procesar_carpeta(
    entrada: Path,
    salida: Path,
    *,
    proyecto: str = "INDESIAHACK",
    proveedores: list[str] | None = None,
    dataset: str = "real",
    trabajo: Path | None = None,
    procesos: int = 1,
    tags: list[str] | None = None,
    evidencias: Path | None = None,
) -> list[Fila]:
    """Procesa todos los equipos de `entrada` y deja resultados y resumen en `salida`."""
    if dataset not in DATASETS:
        # Un nombre mal escrito («sintetico») leería los ejemplos como planos reales sin avisar.
        raise ValueError(f"dataset debe ser uno de {', '.join(DATASETS)}, no {dataset!r}")
    salida = Path(salida)
    configurar_cache(Path(trabajo) if trabajo else salida / "_trabajo")
    ignorados: list[dict] = []
    grupos = agrupar(Path(entrada), ignorados)
    if tags:
        wanted = {t.upper() for t in tags}
        grupos = {t: r for t, r in grupos.items() if t.upper() in wanted}
    opciones = {
        "proyecto": proyecto,
        "proveedores": proveedores,
        "dataset": dataset,
    }
    if evidencias is not None:
        from .lectura.evidencias import cargar

        opciones["evidencias"] = cargar(evidencias)
    tareas = [(tag, revisiones, salida, opciones) for tag, revisiones in grupos.items()]
    if procesos > 1 and len(tareas) > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=procesos) as pool:
            bloques = list(pool.map(_uno, tareas))
    else:
        bloques = [_uno(t) for t in tareas]
    filas = [fila for bloque in bloques for fila in bloque]
    _escribir(
        salida / "resumen_documentos.json",
        json.dumps({"ignorados": ignorados}, ensure_ascii=False, indent=2),
    )
    if filas and ignorados:
        fila = filas[0]
        fila.avisos_documentos.extend(
            f"{item['archivo']}: ignorado · {item['motivo']}." for item in ignorados
        )
        fila.avisos += len(ignorados)
    escribir_resumen(filas, salida)
    return filas


FAMILIA_NO_RECONOCIDA = "Familia no reconocida: no se leyó ninguna cota de la envolvente."
SIN_FAMILIA = "Hace falta el tipo de equipo o sus cotas principales para elegir el modelo."
SIN_LECTURA = "Sin lectura en rev{0} o rev{1}: los cambios no se pueden comparar."
_NO_GEOMETRICOS = ("tag", "identifiers.", "attributes.")


def _hay_geometria(candidatos: list[dict]) -> bool:
    return any(not c.get("path", "").startswith(_NO_GEOMETRICOS) for c in candidatos)


def _hay_tipo(candidatos: list[dict]) -> bool:
    return any(c.get("path") == "attributes.equipment_type" for c in candidatos)


def _hay_lectura(candidatos: list[dict] | None) -> bool:
    """Algo leído del plano, además del tag que puede salir del nombre del archivo."""
    return any(c.get("path") != "tag" for c in candidatos or [])


def _documentos_con_error(eventos: list[dict], nombres: list[str]) -> list[str]:
    """Documentos de la revisión con algún evento en error, en orden y sin repetir.

    Algunas etapas (la familia, por ejemplo) ponen en `file` el equipo y no un archivo: no son
    documentos que hayan fallado.
    """
    propios = set(nombres)
    return list(
        dict.fromkeys(
            e["file"] for e in eventos if e.get("status") == "error" and e.get("file") in propios
        )
    )


def escribir_resumen(filas: list[Fila], salida: Path):
    datos = [asdict(f) for f in filas]
    _escribir(Path(salida) / "resumen.json", json.dumps(datos, ensure_ascii=False, indent=2))
    path = Path(salida) / "resumen.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        columnas = list(Fila.__dataclass_fields__)
        writer = csv.DictWriter(handle, fieldnames=columnas)
        writer.writeheader()
        for fila in datos:
            writer.writerow(
                {
                    **fila,
                    "documentos": "; ".join(fila["documentos"]),
                    "documentos_con_error": "; ".join(fila["documentos_con_error"]),
                    "avisos_documentos": "; ".join(fila["avisos_documentos"]),
                }
            )


def _tipo_error(error: str | None) -> str | None:
    """Categoría del error sin su texto, que puede citar valores o tags del plano."""
    if not error:
        return None
    if error.startswith(FAMILIA_NO_RECONOCIDA):
        return "familia_no_reconocida"
    if error.startswith("Faltan datos explícitos:"):
        return "faltan_datos"
    if error.startswith("tipología no soportada:"):
        return "tipologia_no_soportada"
    if error.startswith("IFC inválido"):
        return "ifc_invalido"
    clase = re.match(r"^([A-Z]\w*(?:Error|Exception|Failure|Unavailable))\b", error)
    return clase[1] if clase else "pipeline"


def resumen_compartible(filas: list[Fila]) -> dict:
    """Agregados del lote sin identificadores originales.

    Sin nombres de archivo, rutas, tags reales ni textos de error o avisos: cada equipo pasa a
    `E01`, `E02`… en el orden del lote y los errores quedan como categoría.
    """
    alias = {tag: f"E{i:02d}" for i, tag in enumerate(dict.fromkeys(f.tag for f in filas), 1)}
    segundos = sorted(f.segundos for f in filas)

    def cuenta(valores):
        return dict(sorted(Counter(str(v) for v in valores if v is not None).items()))

    return {
        "revisiones": len(filas),
        "equipos": len(alias),
        "estado": cuenta(f.estado for f in filas),
        "familia": cuenta(f.familia for f in filas),
        "lod": cuenta(f.lod for f in filas),
        "errores": cuenta(_tipo_error(f.error) for f in filas),
        "avisos": sum(f.avisos for f in filas),
        "con_documentos_con_error": sum(1 for f in filas if f.documentos_con_error),
        "segundos": {
            "total": round(sum(segundos), 1),
            "mediana": round(segundos[len(segundos) // 2], 1) if segundos else 0,
            "max": round(segundos[-1], 1) if segundos else 0,
        },
        "por_revision": [
            {
                "equipo": alias[f.tag],
                "orden": i,
                "estado": f.estado,
                "error": _tipo_error(f.error),
                "familia": f.familia,
                "lod": f.lod,
                "boquillas": f.boquillas,
                "campos": f.campos,
                "pendientes": f.pendientes,
                "avisos": f.avisos,
                "documentos_con_error": len(f.documentos_con_error),
                "cambios": f.cambios,
                "segundos": f.segundos,
            }
            for i, f in enumerate(filas, 1)
        ],
    }
