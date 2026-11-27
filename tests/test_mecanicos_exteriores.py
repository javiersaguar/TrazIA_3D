"""Toberas y componentes exteriores de un mecánico, sin tocar la caja principal."""

from trazia.extraction import Candidate, assemble
from trazia.families import parts
from trazia.ifc import build_ifc, validate_ifc
from trazia.ingest import Bundle, EvidenceLine
from trazia.lectura.mecanicos_exteriores import exteriores
from trazia.model import Document, Source


def linea(texto, x=0.2, y=0.2):
    return EvidenceLine(
        text=texto,
        source=Source(
            document_id="GA",
            locator="Texto de prueba",
            page=1,
            bbox=(x, y, x + 0.2, y + 0.02),
            confidence=0.9,
        ),
    )


def _plano():
    return [
        Bundle(
            document=Document(
                id="GA",
                filename="BOMBA-GA9-Rev0.pdf",
                revision="0",
                sha256="0" * 64,
                page_count=1,
            ),
            media_type="pdf",
        )
    ]


def _envolvente(origen):
    candidatos = [
        Candidate(path="attributes.equipment_type", value="pump", unit="1", source=origen),
        Candidate(path="tag", value="P-1", unit="1", source=origen),
    ]
    for eje, valor in zip("xyz", (2000, 800, 900), strict=True):
        candidatos.append(
            Candidate(path=f"envelope.size.{eje}", value=valor, unit="mm", source=origen)
        )
        candidatos.append(
            Candidate(
                path=f"envelope.origin.{eje}",
                value=0,
                unit="mm",
                source=origen.model_copy(update={"rule": "asumido.origen_bancada"}),
                state="assumed",
            )
        )
    return candidatos


def test_bomba_con_tren_y_dos_toberas_de_proceso():
    origen = linea("PUMP").source
    lineas = [
        linea("BASEPLATE"),
        linea("MOTOR"),
        linea("PUMP"),
        linea('SUCTION (10")'),
        linea("N1 10'' FLANGED 300#RF PUMP SUCTION"),
        linea("N2 8'' FLANGED 300#RF PUMP DISCHARGE"),
        linea('D3 2" THREADED NPT BASEPLATE DRAIN'),
    ]
    extra = exteriores(lineas, "pump", (2000, 800, 900), origen)
    revision = assemble(
        _plano(),
        [*_envolvente(origen), *extra],
        project_id="TEST",
        equipment_id="bomba",
        revision="0",
        dataset="synthetic",
    )
    equipo = revision.equipment
    assert [p.id for p in equipo.components] == ["bancada", "motor", "maquina"]
    assert {n.id for n in equipo.nozzles} == {"N1", "N2"}
    assert equipo.nozzles[0].position is not None
    assert "D3" not in {n.id for n in equipo.nozzles}
    assert equipo.envelope.size.x.value == 2000
    assert (
        "components"
        not in assemble(
            _plano(),
            _envolvente(origen),
            project_id="TEST",
            equipment_id="bomba",
            revision="0",
        ).model_dump(mode="json")["equipment"]
    )
    modelo = build_ifc(revision, draft=True)
    assert modelo.by_type("IfcPump")
    assert len(modelo.by_type("IfcPipeSegment")) == 2
    assert len(parts(equipo)) >= 4
    assert not validate_ifc(modelo)


def test_compresor_coloca_la_tabla_de_puntos_y_descarta_la_que_no_cabe():
    origen = linea("COMPRESSOR").source
    lineas = [
        linea("ELECTRIC MOTOR"),
        linea("GEARBOX"),
        linea("BASEPLATE 4000"),
        linea("TP900 (1ST) COMPRESSOR SUCTION 26'' 300# RF R9 400* 0* 500*"),
        linea("TP133 COUPLING VENT HOLD'' 150# RF R9 10* 0* 10*"),
        linea("TP901 (1ST) COMPRESSOR DISCHARGE 18'' 300# RF R9 9000* 0* 500*"),
    ]
    extra = exteriores(lineas, "compressor", (4000, 1500, 1600), origen)
    revision = assemble(
        _plano(),
        [
            Candidate(
                path="attributes.equipment_type", value="compressor", unit="1", source=origen
            ),
            Candidate(path="tag", value="K-1", unit="1", source=origen),
            *[
                Candidate(path=f"envelope.size.{eje}", value=valor, unit="mm", source=origen)
                for eje, valor in zip("xyz", (4000, 1500, 1600), strict=True)
            ],
            *[
                Candidate(
                    path=f"envelope.origin.{eje}",
                    value=0,
                    unit="mm",
                    source=origen.model_copy(update={"rule": "asumido.origen_bancada"}),
                    state="assumed",
                )
                for eje in "xyz"
            ],
            *extra,
        ],
        project_id="TEST",
        equipment_id="compresor",
        revision="0",
    )
    ids = {n.id for n in revision.equipment.nozzles}
    assert "TP900" in ids
    assert "TP901" not in ids
    assert "TP133" not in ids
    assert {p.id for p in revision.equipment.components} == {
        "bancada",
        "motor",
        "reductora",
        "maquina",
    }
    assert not validate_ifc(build_ifc(revision, draft=True))
