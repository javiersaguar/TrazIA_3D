"""Calco de una vista de un plano vectorial a milímetros del modelo.

Una vista se describe en un JSON (fuera de Git si cita un plano real):

    {"pdf": "EQUIPO-Rev0.pdf", "page": 1, "bbox": [x0, top, x1, bottom],
     "u": {"axis": "x", "pdf": [p0, p1], "mm": [m0, m1]},
     "v": {"axis": "z", "pdf": [t0, t1], "mm": [m0, m1]},
     "depth": {"axis": "y", "toward_viewer": -1}}

`bbox`, `u.pdf` y `v.pdf` van en puntos de pdfplumber (origen arriba a la izquierda). Cada eje
se calibra con dos cotas rotuladas de esa misma vista, porque un GA no siempre está a escala
entre vistas. `depth.toward_viewer` es el signo del eje de profundidad que mira al observador.

    python scripts/calcar_vista.py recorte VISTA.json DATASET -o recorte.png [--paso 100]
    python scripts/calcar_vista.py lineas VISTA.json DATASET [--min 20] [--zona u0 v0 u1 v1]

`recorte` dibuja la vista con una rejilla en mm del modelo; `lineas` lista los trazos rectos y
las curvas de la zona ya convertidos a mm, para leer contornos exactos en vez de medir a ojo.
"""

import argparse
import json
from pathlib import Path

import pdfplumber
from PIL import ImageDraw


class Vista:
    def __init__(self, cfg: dict, dataset: Path):
        self.cfg = cfg
        directa = dataset / "mechanical" / cfg["pdf"]
        self.pdf_path = directa if directa.exists() else next(dataset.rglob(cfg["pdf"]))
        self.page_no = cfg.get("page", 1)
        self.bbox = cfg["bbox"]
        (p0, p1), (m0, m1) = cfg["u"]["pdf"], cfg["u"]["mm"]
        self.ku, self.bu = (m1 - m0) / (p1 - p0), m0 - (m1 - m0) / (p1 - p0) * p0
        (t0, t1), (n0, n1) = cfg["v"]["pdf"], cfg["v"]["mm"]
        self.kv, self.bv = (n1 - n0) / (t1 - t0), n0 - (n1 - n0) / (t1 - t0) * t0

    def mm(self, x: float, top: float) -> tuple[float, float]:
        return self.ku * x + self.bu, self.kv * top + self.bv

    def pdf(self, u: float, v: float) -> tuple[float, float]:
        return (u - self.bu) / self.ku, (v - self.bv) / self.kv

    def open(self):
        doc = pdfplumber.open(str(self.pdf_path))
        return doc, doc.pages[self.page_no - 1]


def recorte(vista: Vista, salida: Path, paso: float, dpi: int, zona=None):
    if zona:
        (xa, ta), (xb, tb) = vista.pdf(zona[0], zona[1]), vista.pdf(zona[2], zona[3])
        vista.bbox = [min(xa, xb), min(ta, tb), max(xa, xb), max(ta, tb)]
    doc, page = vista.open()
    with doc:
        crop = page.crop(vista.bbox)
        im = crop.to_image(resolution=dpi).original.convert("RGB")
    d = ImageDraw.Draw(im)
    s = dpi / 72
    x0, t0, x1, t1 = vista.bbox
    u_lo, v_hi = vista.mm(x0, t0)
    u_hi, v_lo = vista.mm(x1, t1)
    u_lo, u_hi = sorted((u_lo, u_hi))
    v_lo, v_hi = sorted((v_lo, v_hi))
    u = (u_lo // paso) * paso
    while u <= u_hi:
        px = (vista.pdf(u, 0)[0] - x0) * s
        d.line([(px, 0), (px, im.height)], fill=(0, 160, 255) if u % (paso * 5) else (255, 0, 0))
        d.text((px + 2, 2), f"{u:.0f}", fill=(255, 0, 0))
        u += paso
    v = (v_lo // paso) * paso
    while v <= v_hi:
        py = (vista.pdf(0, v)[1] - t0) * s
        d.line([(0, py), (im.width, py)], fill=(0, 160, 255) if v % (paso * 5) else (255, 0, 0))
        d.text((2, py + 2), f"{v:.0f}", fill=(255, 0, 0))
        v += paso
    im.save(salida)
    print(f"{salida} {im.width}x{im.height}")


def lineas(vista: Vista, min_len: float, zona):
    doc, page = vista.open()
    with doc:
        crop = page.crop(vista.bbox)
        objetos = [("l", o) for o in crop.lines] + [("c", o) for o in crop.curves]
        objetos += [("r", o) for o in crop.rects]
    filas = []
    for tipo, o in objetos:
        pts = [vista.mm(x, top) for x, top in o.get("pts", [])] or [
            vista.mm(o["x0"], o["top"]),
            vista.mm(o["x1"], o["bottom"]),
        ]
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        if zona and not (
            min(us) >= zona[0] and max(us) <= zona[2] and min(vs) >= zona[1] and max(vs) <= zona[3]
        ):
            continue
        largo = max(max(us) - min(us), max(vs) - min(vs))
        if largo < min_len:
            continue
        if tipo == "l" and len(pts) == 2:
            (a, b), (c, e) = pts
            forma = "H" if abs(b - e) < 1 else "V" if abs(a - c) < 1 else "D"
            filas.append(
                (forma, round(min(a, c)), round(min(b, e)), round(max(a, c)), round(max(b, e)))
            )
        else:
            filas.append(
                (tipo.upper(), round(min(us)), round(min(vs)), round(max(us)), round(max(vs)))
            )
    for f in sorted(set(filas)):
        print(*f)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for nombre in ("recorte", "lineas"):
        p = sub.add_parser(nombre)
        p.add_argument("vista", type=Path)
        p.add_argument("dataset", type=Path)
        if nombre == "recorte":
            p.add_argument("-o", "--salida", type=Path, required=True)
            p.add_argument("--paso", type=float, default=100.0)
            p.add_argument("--dpi", type=int, default=200)
        else:
            p.add_argument("--min", type=float, default=20.0)
        p.add_argument("--zona", type=float, nargs=4, help="u0 v0 u1 v1 en mm del modelo")
    args = parser.parse_args()
    vista = Vista(json.loads(args.vista.read_text(encoding="utf-8")), args.dataset)
    if args.cmd == "recorte":
        recorte(vista, args.salida, args.paso, args.dpi, args.zona)
    else:
        lineas(vista, args.min, args.zona)


if __name__ == "__main__":
    main()
