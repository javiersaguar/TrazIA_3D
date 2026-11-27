"""Comprobación de la entrega del viernes (27/11, 10:00) desde `main` congelado (D5).

    uv run python scripts/entrega.py                    # repo, autoría y datos (segundos)
    uv run python scripts/entrega.py --clon             # además, un clon limpio de origin/main
    uv run python scripts/entrega.py --clon --sin-pruebas --datos data/Dataset-tecnicasreunidas

Cada línea es ✓ (bien), ! (aviso: revisar, no bloquea) o ✗ (fallo: no entregar así).

En el repo:

- árbol limpio, en `main` e igual a `origin/main`, y `origin` en el GitLab del evento;
- `PREVIOUS_WORK.md` sin «pendiente» y con el tag `pre-hackathon-baseline` y su commit. El tag
  vive en el repo previo (trazia-3d); aquí basta con que el registro lo cite;
- autores y committers desde la plantilla de la organización en `.github/autores.txt`, con el
  nombre de una de las cuatro personas, y ningún coautor ni firma de asistente;
- ningún PDF, IFC ni Excel versionado fuera de `examples/` y de `.guardian-permitidos` (lo
  permitido sale como aviso, para confirmar que es sintético), nada de `data/` ni `generated/`,
  y el guardián de datos en verde;
- con `--pitch`, el pitch compila y tiene las cifras del evento.

Con `--clon`, en una carpeta nueva fuera del repo:

- `git clone` de `origin` en `main` y `uv sync --frozen` con los extras de AGENTS.md;
- `pytest -q` completo, salvo con `--sin-pruebas`. En un portátil justo de memoria conviene
  lanzarlo en otra máquina (docs/INCIDENCIAS.md, I-05);
- `trazia lote` sobre los ejemplos sintéticos: V-101 debe dar dos revisiones `ok`;
- con `--datos`, `trazia lote` sobre un equipo real (`--tag`, por defecto BF-V-0016);
- la API arranca y `/health` responde.
"""

import argparse
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TAG = "pre-hackathon-baseline"
# Último commit de la plantilla que dio la organización: la autoría se mide desde aquí.
BASE_PLANTILLA = "1eeae5e"
FIRMAS = re.compile(r"co-authored-by|generated with|🤖", re.I)
NOMBRES_EQUIPO = ("javier", "miguel", "iria", "alejandro")
EXTENSIONES_TR = {".pdf", ".ifc", ".xlsx", ".xls", ".dwg", ".dxf"}
EXTRAS = ("dev", "ocr", "geo", "api")


def git(*argumentos: str, cwd: Path | None = None) -> tuple[int, str]:
    proceso = subprocess.run(
        ["git", *argumentos],
        cwd=cwd or RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proceso.returncode, proceso.stdout.strip()


class Informe:
    def __init__(self):
        self.fallos = self.avisos = 0

    def ok(self, texto):
        print(f"✓ {texto}")

    def aviso(self, texto):
        self.avisos += 1
        print(f"! {texto}")

    def fallo(self, texto):
        self.fallos += 1
        print(f"✗ {texto}")

    def si(self, condicion, bien, mal, *, grave=True):
        if condicion:
            self.ok(bien)
        elif grave:
            self.fallo(mal)
        else:
            self.aviso(mal)


def autores_permitidos() -> set[str]:
    path = RAIZ / ".github" / "autores.txt"
    lineas = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return {x.strip().lower() for x in lineas if x.strip() and not x.startswith("#")}


# --- Repo ------------------------------------------------------------------------------------


def comprobar_git(informe: Informe) -> None:
    _, estado = git("status", "--porcelain")
    informe.si(not estado, "Árbol limpio", "Hay cambios sin confirmar")
    _, rama = git("branch", "--show-current")
    informe.si(rama == "main", "En main", f"Estás en «{rama}», no en main")
    _, remotos = git("remote")
    _, cabeza = git("rev-parse", "HEAD")
    for remoto in [r for r in ("origin", "gitlab") if r in remotos.split()]:
        if git("fetch", "--tags", remoto)[0] != 0:
            informe.aviso(f"No se pudo leer {remoto} (¿sin red?)")
            continue
        _, remota = git("rev-parse", f"{remoto}/main")
        informe.si(cabeza == remota, f"main = {remoto}/main", f"main no coincide con {remoto}/main")
        codigo, tags = git("ls-remote", "--tags", remoto, TAG)
        informe.si(
            codigo == 0 and TAG in tags,
            f"Tag en {remoto}",
            f"El tag {TAG} no está en {remoto}: vive en el repo previo y lo cita PREVIOUS_WORK.md",
            grave=False,
        )
    _, url = git("remote", "get-url", "origin")
    informe.si(
        "gitlab" in url.lower(),
        "origin apunta al GitLab del evento",
        f"origin no es GitLab ({url or 'sin origin'}): la entrega oficial va a GitLab",
        grave=False,
    )


def comprobar_registro(informe: Informe) -> None:
    texto = (RAIZ / "PREVIOUS_WORK.md").read_text(encoding="utf-8")
    pendientes = [  # líneas del registro («- Tag publicado: pendiente.»), no títulos
        linea.strip() for linea in texto.splitlines() if re.match(r"^- .*: pendiente\.?\s*$", linea)
    ]
    informe.si(
        not pendientes,
        "PREVIOUS_WORK.md cerrado",
        "PREVIOUS_WORK.md tiene pendientes: " + " | ".join(pendientes[:4]),
    )
    informe.si(
        TAG in texto and re.search(r"\b[0-9a-f]{40}\b", texto) is not None,
        f"PREVIOUS_WORK.md cita el tag {TAG} y su commit",
        f"PREVIOUS_WORK.md no cita el tag {TAG} con el commit completo",
    )


def _rango_autoria() -> str:
    if git("tag", "-l", TAG)[1]:
        return f"{TAG}..HEAD"
    if git("rev-parse", "--verify", "--quiet", f"{BASE_PLANTILLA}^{{commit}}")[0] == 0:
        return f"{BASE_PLANTILLA}..HEAD"
    return "HEAD"


def comprobar_autoria(informe: Informe) -> None:
    rango = _rango_autoria()
    _, salida = git("log", rango, "--format=%H%x1f%an%x1f%ae%x1f%ce%x1f%B%x1e")
    permitidos = autores_permitidos()
    extranos, firmados, nombres = set(), [], set()
    for bloque in filter(str.strip, salida.split("\x1e")):
        sha, nombre, autor, committer, mensaje = bloque.strip().split("\x1f", 4)
        extranos |= {c for c in (autor.lower(), committer.lower()) if c not in permitidos}
        if FIRMAS.search(mensaje):
            firmados.append(sha[:10])
        if not any(n in nombre.lower() for n in NOMBRES_EQUIPO):
            nombres.add(nombre)
    informe.si(
        not extranos,
        f"Autores en .github/autores.txt ({rango})",
        f"Correos fuera de .github/autores.txt: {', '.join(sorted(extranos))}",
    )
    informe.si(
        not firmados,
        "Sin coautores ni firmas en los mensajes",
        f"Commits con coautor o firma: {', '.join(firmados[:8])}",
    )
    informe.si(
        not nombres,
        "Nombres de autor del equipo",
        f"Nombres de autor que no son del equipo: {', '.join(sorted(nombres))}",
        grave=False,
    )
    autores = (RAIZ / ".github" / "autores.txt").read_text(encoding="utf-8").lower()
    if "pendiente" in autores:
        informe.aviso(".github/autores.txt aún tiene correos pendientes del equipo")


def _permitidos() -> list[str]:
    """Patrones de `.guardian-permitidos`: material sintético o de demo acordado por el equipo."""
    path = RAIZ / ".guardian-permitidos"
    lineas = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return [x.strip() for x in lineas if x.strip() and not x.lstrip().startswith("#")]


def comprobar_datos(informe: Informe) -> None:
    from guardian_datos import esta_permitido

    _, archivos = git("ls-files")
    rutas = [r for r in archivos.splitlines() if r]
    documentos = [
        r
        for r in rutas
        if Path(r).suffix.lower() in EXTENSIONES_TR and not r.startswith("examples/")
    ]
    patrones = _permitidos()
    sin_permiso = [r for r in documentos if not esta_permitido(r, patrones)]
    informe.si(
        not sin_permiso,
        "Ningún PDF, IFC ni Excel versionado fuera de examples/ y .guardian-permitidos",
        f"Documentos versionados sin permiso: {', '.join(sin_permiso[:8])}",
    )
    if permitidos := len(documentos) - len(sin_permiso):
        carpetas = sorted({r.split("/", 1)[0] for r in documentos if r not in sin_permiso})
        informe.aviso(
            f"{permitidos} documentos fuera de examples/ admitidos por .guardian-permitidos "
            f"({', '.join(carpetas)}): confirmar que son sintéticos"
        )
    locales = [r for r in rutas if r.split("/", 1)[0] in ("data", "generated")]
    informe.si(
        not locales,
        "Nada de data/ ni generated/ en Git",
        f"Versionado en data/ o generated/: {', '.join(locales[:8])}",
    )
    guardian_py = RAIZ / "scripts" / "guardian_datos.py"
    if not guardian_py.is_file():
        informe.aviso("No hay scripts/guardian_datos.py en este repo")
        return
    guardian = subprocess.run(
        [sys.executable, str(guardian_py), "--todo"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    informe.si(
        guardian.returncode == 0,
        "Guardián de datos en verde",
        "Guardián de datos en rojo:\n" + (guardian.stdout + guardian.stderr)[-1200:],
    )


def comprobar_pitch(informe: Informe, compilar: bool) -> None:
    cifras = RAIZ / "pitch" / "cifras-evento.js"
    texto = cifras.read_text(encoding="utf-8") if cifras.is_file() else ""
    informe.si(
        bool(texto) and "cifrasEvento = null" not in texto,
        "El pitch tiene las cifras del evento",
        "El pitch solo tiene cifras sintéticas: python -m bench.cifras aplicar cifras_evento.json",
        grave=False,
    )
    if compilar:
        corepack = shutil.which("corepack") or "corepack"  # en Windows es corepack.cmd
        proceso = subprocess.run(
            [corepack, "pnpm@10.18.0", "build"],
            cwd=RAIZ / "pitch" / "track",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        informe.si(
            proceso.returncode == 0,
            "El pitch compila",
            "El pitch no compila:\n" + (proceso.stdout + proceso.stderr)[-1500:],
        )


# --- Clon limpio -----------------------------------------------------------------------------


def _ejecutar(orden: list[str], cwd: Path, *, timeout: int, env=None):
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})}
    entorno.pop("VIRTUAL_ENV", None)  # el clon usa su propio .venv, no el de este repo
    try:
        return subprocess.run(
            orden,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=entorno,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(orden, 124, exc.stdout or "", f"Tiempo agotado: {exc}")


def _resumen(salida: Path) -> list[dict]:
    path = salida / "resumen.json"
    if not path.is_file():
        return []
    datos = json.loads(path.read_text(encoding="utf-8"))
    return datos.get("filas", []) if isinstance(datos, dict) else datos


def _borrar(carpeta: Path) -> None:
    """Borra el clon temporal. En Windows, git deja los packs de solo lectura."""

    def _forzar(funcion, ruta, _error):
        os.chmod(ruta, stat.S_IWRITE)
        funcion(ruta)

    if sys.version_info >= (3, 12):
        shutil.rmtree(carpeta, onexc=_forzar)
    else:  # Python 3.11
        shutil.rmtree(carpeta, onerror=_forzar)


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _python_del_clon(clon: Path) -> Path:
    windows = clon / ".venv" / "Scripts" / "python.exe"
    return windows if windows.is_file() else clon / ".venv" / "bin" / "python"


def _cerrar_arbol(proceso: subprocess.Popen) -> None:
    """Cierra el proceso y sus hijos. En Windows, el python.exe de un venv lanza otro proceso,
    y `terminate` dejaría vivo al servidor."""
    if proceso.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proceso.pid)], capture_output=True, check=False
        )
    else:
        proceso.terminate()
    try:
        proceso.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proceso.kill()
        proceso.wait(timeout=20)


def comprobar_api(informe: Informe, clon: Path, trabajo: Path) -> None:
    puerto = _puerto_libre()
    entorno = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "TRAZIA_PORT": str(puerto),
        "TRAZIA_DATA": str(trabajo / "api_datos"),
    }
    entorno.pop("VIRTUAL_ENV", None)
    registro = trabajo / "api.log"
    with registro.open("w", encoding="utf-8") as salida:
        proceso = subprocess.Popen(
            [str(_python_del_clon(clon)), "-m", "trazia.api"],
            cwd=clon,
            env=entorno,
            stdout=salida,
            stderr=subprocess.STDOUT,
        )
        respuesta, limite = None, time.monotonic() + 120
        try:
            while time.monotonic() < limite and proceso.poll() is None:
                try:
                    url = f"http://127.0.0.1:{puerto}/health"
                    with urllib.request.urlopen(url, timeout=3) as r:
                        respuesta = json.loads(r.read().decode("utf-8"))
                        break
                except OSError:
                    time.sleep(2)
        finally:
            _cerrar_arbol(proceso)
    error = registro.read_text(encoding="utf-8", errors="replace")
    informe.si(
        bool(respuesta) and respuesta.get("status") == "ok",
        "La API arranca y /health responde",
        "La API no responde en /health:\n" + (error or "")[-1200:],
    )


def comprobar_clon(
    informe: Informe,
    *,
    destino: Path | None,
    pruebas: bool,
    datos: Path | None,
    tag: str,
    conservar: bool,
) -> None:
    uv = shutil.which("uv")
    if not uv:
        informe.fallo("No encuentro uv en el PATH: no se puede comprobar el clon")
        return
    _, url = git("remote", "get-url", "origin")
    base = Path(tempfile.mkdtemp(prefix="trazia-entrega-")) if destino is None else destino
    clon, trabajo = base / "hack-tc02", base / "trabajo"
    if clon.exists():
        informe.fallo(f"{clon} ya existe: elige otra carpeta con --destino")
        return
    trabajo.mkdir(parents=True, exist_ok=True)
    print(f"  clon en {clon}")
    try:
        r = _ejecutar(["git", "clone", "--branch", "main", url, str(clon)], base, timeout=600)
        informe.si(r.returncode == 0, "Clon limpio de origin/main", "git clone falló:\n" + r.stderr)
        if r.returncode != 0:
            return
        extras = [a for e in EXTRAS for a in ("--extra", e)]
        r = _ejecutar([uv, "sync", "--frozen", *extras], clon, timeout=1800)
        informe.si(
            r.returncode == 0,
            "uv sync --frozen con los extras de AGENTS.md",
            "uv sync falló:\n" + (r.stdout + r.stderr)[-1500:],
        )
        if r.returncode != 0:
            return
        if pruebas:
            r = _ejecutar(
                [uv, "run", "--frozen", "pytest", "-q", "-p", "no:cacheprovider"],
                clon,
                timeout=3600,
            )
            ultima = (r.stdout.strip().splitlines() or [""])[-1]
            informe.si(r.returncode == 0, f"pytest -q: {ultima}", f"pytest -q falló: {ultima}")
        else:
            informe.aviso("pytest -q no se ha ejecutado (--sin-pruebas)")
        salida = trabajo / "lote_ejemplos"
        r = _ejecutar(
            [
                uv,
                "run",
                "--frozen",
                "trazia",
                "lote",
                "examples/documents",
                "-o",
                str(salida),
                "--dataset",
                "synthetic",
            ],
            clon,
            timeout=900,
        )
        estados = [f.get("estado") for f in _resumen(salida)]
        informe.si(
            estados == ["ok", "ok"],
            "trazia lote sobre los ejemplos: V-101 en dos revisiones ok",
            f"trazia lote sobre los ejemplos: {estados or 'sin resumen'}\n" + r.stderr[-800:],
        )
        if datos is not None:
            salida = trabajo / "lote_real"
            r = _ejecutar(
                [
                    uv,
                    "run",
                    "--frozen",
                    "trazia",
                    "lote",
                    str(datos.resolve()),
                    "-o",
                    str(salida),
                    "--dataset",
                    "real",
                    "--tag",
                    tag,
                ],
                clon,
                timeout=1800,
            )
            filas = _resumen(salida)
            errores = [
                f"rev{f.get('revision')}: {f.get('error')}"
                for f in filas
                if f.get("estado") == "error"
            ]
            informe.si(
                bool(filas) and not errores,
                f"trazia lote sobre {tag}: "
                + ", ".join(f"rev{f.get('revision')} {f.get('estado')}" for f in filas),
                f"trazia lote sobre {tag} con errores: {errores or 'sin resumen'}",
            )
        comprobar_api(informe, clon, trabajo)
    finally:
        if conservar or destino is not None:
            print(f"  se conserva {base}")
        else:
            _borrar(base)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Comprobar la entrega (D5)")
    parser.add_argument("--clon", action="store_true", help="Comprobar un clon limpio de main")
    parser.add_argument("--sin-pruebas", action="store_true", help="En el clon, sin pytest -q")
    parser.add_argument("--datos", type=Path, help="Dataset de TR para un lote real en el clon")
    parser.add_argument("--tag", default="BF-V-0016", help="Equipo del lote real (BF-V-0016)")
    parser.add_argument("--destino", type=Path, help="Carpeta del clon (por defecto, temporal)")
    parser.add_argument("--conservar", action="store_true", help="No borrar el clon temporal")
    parser.add_argument("--pitch", action="store_true", help="Compilar también el pitch")
    args = parser.parse_args(argv)
    informe = Informe()
    comprobar_git(informe)
    comprobar_registro(informe)
    comprobar_autoria(informe)
    comprobar_datos(informe)
    comprobar_pitch(informe, args.pitch)
    if args.clon:
        comprobar_clon(
            informe,
            destino=args.destino,
            pruebas=not args.sin_pruebas,
            datos=args.datos,
            tag=args.tag,
            conservar=args.conservar,
        )
    print()
    if informe.fallos:
        print(f"No entregar todavía: {informe.fallos} fallos y {informe.avisos} avisos.")
        return 1
    print(f"Lista para entregar ({informe.avisos} avisos que revisar).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
