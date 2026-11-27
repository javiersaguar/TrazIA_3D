"""Uniones soldadas deducidas de piezas citadas, con candidatos sintéticos."""

from trazia.extraction import Candidate
from trazia.lectura.soldaduras import inferir
from trazia.model import Source


def _c(path, value, unit="mm", confianza=0.9):
    fuente = Source(
        document_id="GA-EJ-V-01", page=1, locator=f"{path} {value}", confidence=confianza
    )
    return Candidate(path=path, value=value, unit=unit, source=fuente)


def _uniones(candidatos):
    uniones: dict[str, dict] = {}
    for c in inferir(candidatos):
        _, ident, campo = c.path.split(".", 2)
        uniones.setdefault(ident, {})[campo] = c
    return uniones


def test_vertical_con_tapa_embridada_y_boquillas():
    uniones = _uniones(
        [
            _c("diameter", 800.0),
            _c("height", 1925.0),
            _c("head_depth", 257.0),
            _c("attributes.upper_closure", "blind_flange", "1"),
            _c("nozzles.N1.size_nps", 2.0, "in"),
            _c("nozzles.N2.rating", "300#", "1"),
        ]
    )
    assert set(uniones) == {
        "W:SHELL|HEAD_BOTTOM",
        "W:SHELL|BODY_FLANGE",
        "W:N1|SHELL",
        "W:N2|SHELL",
    }
    assert uniones["W:SHELL|HEAD_BOTTOM"]["elevation_mm"].value == 0.0
    assert uniones["W:SHELL|BODY_FLANGE"]["elevation_mm"].value == 1925.0
    assert uniones["W:N1|SHELL"]["kind"].value == "nozzle"
    assert uniones["W:N1|SHELL"]["joins"].value == "N1|SHELL"
    # Lleva la cita de la pieza, su regla y una confianza que no supera la de lo deducido.
    fuente = uniones["W:SHELL|BODY_FLANGE"]["kind"].source
    assert fuente.rule == "soldadura.virola_brida" and fuente.page == 1
    assert fuente.confidence <= 0.55


def test_virolas_consecutivas_sin_diametro_leido():
    candidatos = [_c(f"shell.courses.V{i:02d}.height", 3000.0) for i in (1, 2, 3)]
    uniones = _uniones(candidatos)
    assert {"W:V01|V02", "W:V02|V03", "W:SHELL|HEAD_BOTTOM", "W:SHELL|HEAD_TOP"} == set(uniones)
    # Sin saber qué virola está abajo, la costura entre virolas no lleva cota.
    assert "elevation_mm" not in uniones["W:V01|V02"]
    assert uniones["W:V01|V02"]["kind"].value == "circumferential"


def test_horizontal_tiene_dos_fondos_en_las_tangentes():
    uniones = _uniones([_c("horizontal.diameter", 1900.0), _c("horizontal.length", 5700.0)])
    assert uniones["W:SHELL|HEAD_LEFT"]["elevation_mm"].value == 0.0
    assert uniones["W:SHELL|HEAD_RIGHT"]["elevation_mm"].value == 5700.0


def test_tanque_por_anillos():
    candidatos = [_c(f"tank.courses.{n}.thickness", 10.0) for n in (1, 2, 3)]
    candidatos.append(_c("nozzles.N1.size_nps", 4.0, "in"))
    uniones = _uniones(candidatos)
    assert {"W:C1|C2", "W:C2|C3", "W:C1|BOTTOM", "W:N1|TANK"} == set(uniones)


def test_el_id_no_cambia_entre_revisiones():
    rev1 = [_c("diameter", 800.0), _c("height", 1925.0), _c("nozzles.N1.size_nps", 2.0, "in")]
    rev2 = [_c("diameter", 800.0), _c("height", 1940.0), _c("nozzles.N1.size_nps", 3.0, "in")]
    assert set(_uniones(rev1)) == set(_uniones(rev2))


def test_sin_piezas_no_hay_uniones():
    assert inferir([_c("attributes.weight_empty", 2100.0, "kg")]) == []


def test_horizontal_con_cadena_de_tramos_suelda_tras_la_faldilla():
    # 80V01 sintético: S.F. 50 + 1655 + 1980 + 1965 + S.F. 50 = 5700 T.L.–T.L.
    candidatos = [_c("horizontal.diameter", 1900.0), _c("horizontal.length", 5700.0)]
    for pos, largo, estacion in (
        ("1-2", 1655.0, 50.0),
        ("1-3", 1980.0, 1705.0),
        ("1-4", 1965.0, 3685.0),
    ):
        candidatos += [
            _c(f"shell.courses.{pos}.height", largo),
            _c(f"shell.courses.{pos}.station", estacion),
        ]
    uniones = _uniones(candidatos)
    cotas = {ident: u["elevation_mm"].value for ident, u in uniones.items()}
    assert cotas == {
        "W:1-2|1-3": 1705.0,
        "W:1-3|1-4": 3685.0,
        "W:SHELL|HEAD_LEFT": 50.0,
        "W:SHELL|HEAD_RIGHT": 5650.0,
    }


def test_vertical_con_faldilla_recta_desplaza_las_costuras():
    # BF-V-0016: «H= 257 mm; h= 50mm» y chapa de 1925 de desarrollo; F.F. a 2100 de la T.L.
    uniones = _uniones(
        [
            _c("diameter", 800.0),
            _c("height", 2100.0),
            _c("attributes.shell_height", 1925.0),
            _c("attributes.head_straight_flange", 50.0),
            _c("attributes.upper_closure", "blind_flange", "1"),
        ]
    )
    assert uniones["W:SHELL|HEAD_BOTTOM"]["elevation_mm"].value == 50.0
    assert uniones["W:SHELL|BODY_FLANGE"]["elevation_mm"].value == 1975.0
