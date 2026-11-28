"""Superpone un modelo IFC sobre las vistas calibradas del plano del que sale.

Usa las mismas vistas JSON que `calcar_vista.py`. Para cada vista proyecta los sólidos del IFC
en sus dos ejes, los pinta del más lejano al más cercano y los mezcla al 50 % sobre el plano.
Así se ve de un vistazo si cada pieza cae sobre su dibujo.

    python scripts/superponer_vistas.py MODELO.ifc VISTAS_DIR DATASET -o SALIDA_DIR
"""

import argparse
import json
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from calcar_vista import Vista  # noqa: E402

COLORES = {
    "IfcPump": (220, 40, 40),
    "IfcCompressor": (220, 40, 40),
    "IfcElectricMotor": (30, 100, 230),
    "IfcPlate": (120, 120, 120),
    "IfcPipeSegment": (0, 170, 0),
    "IfcJunctionBox": (245, 150, 0),
    "IfcUnitaryEquipment": (150, 40, 190),
    "IfcFooting": (170, 170, 170),
    "IfcTank": (0, 150, 130),
    "IfcFilter": (230, 110, 0),
    "IfcHeatExchanger": (0, 180, 160),
    "IfcMember": (100, 110, 120),
    "IfcValve": (200, 60, 160),
    "IfcSensor": (0, 120, 200),
    "IfcPipeFitting": (0, 140, 60),
    "IfcMechanicalFastener": (90, 90, 90),
    "IfcDiscreteAccessory": (160, 120, 60),
    "IfcColumn": (150, 150, 150),
    "IfcBeam": (120, 90, 160),
    "IfcSlab": (185, 185, 185),
    "IfcRailing": (230, 170, 0),
}
OTRO = (190, 140, 40)


def triangulos(modelo: Path) -> list:
    ajustes = ifcopenshell.geom.settings()
    ajustes.set("use-world-coords", True)
    out = []
    for e in ifcopenshell.open(str(modelo)).by_type("IfcElement"):
        if not e.Representation or e.ObjectType == "BOLT":
            continue
        forma = ifcopenshell.geom.create_shape(ajustes, e)  # mantener viva la forma
        g = forma.geometry
        v = [tuple(g.verts[i : i + 3]) for i in range(0, len(g.verts), 3)]
        color = COLORES.get(e.is_a(), OTRO)
        for i in range(0, len(g.faces), 3):
            out.append(([v[g.faces[i + n]] for n in range(3)], color))
    return out


def superponer(vista: Vista, tris: list, dpi: int) -> Image.Image:
    doc, page = vista.open()
    with doc:
        plano = page.crop(vista.bbox).to_image(resolution=dpi).original.convert("RGB")
    s = dpi / 72
    x0, t0 = vista.bbox[0], vista.bbox[1]
    iu, iv = "xyz".index(vista.cfg["u"]["axis"]), "xyz".index(vista.cfg["v"]["axis"])
    prof = vista.cfg["depth"]
    ip, signo = "xyz".index(prof["axis"]), prof["toward_viewer"]
    capa = Image.new("RGBA", plano.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for pts, color in sorted(tris, key=lambda t: signo * sum(p[ip] for p in t[0])):
        poly = []
        for p in pts:
            x, top = vista.pdf(p[iu] * 1000, p[iv] * 1000)
            poly.append(((x - x0) * s, (top - t0) * s))
        d.polygon(poly, fill=(*color, 255))
    capa.putalpha(capa.getchannel("A").point(lambda a: 120 if a else 0))
    return Image.alpha_composite(plano.convert("RGBA"), capa).convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("modelo", type=Path)
    parser.add_argument("vistas", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("-o", "--salida", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    tris = triangulos(args.modelo)
    for ruta in sorted(args.vistas.glob("*.json")):
        vista = Vista(json.loads(ruta.read_text(encoding="utf-8")), args.dataset)
        destino = args.salida / f"{ruta.stem}.png"
        superponer(vista, tris, args.dpi).save(destino)
        print(destino)


if __name__ == "__main__":
    main()
