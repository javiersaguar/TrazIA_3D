from trazia.etiquetas import etiqueta


def test_etiquetas_legibles_como_en_la_web():
    assert etiqueta("horizontal.diameter") == "Diámetro de la virola"
    assert etiqueta("nozzles.M1.rating") == "Boquilla M1 · Clase de brida"
    assert etiqueta("shell.courses.V03.thickness") == "Virola V03 · Espesor"
    assert etiqueta("column.sections.V11.diameter") == "Tramo de columna V11 · Diámetro"
    assert etiqueta("horizontal.saddle_positions.0") == "Silleta 1 · Posición"
    assert etiqueta("welds.W:K1|SHELL.kind") == "Soldadura K1 – SHELL · Tipo"
    assert etiqueta("attributes.skirt_diameter") == "Diámetro del faldón"
    assert etiqueta("attributes.algo_nuevo") == "Algo nuevo"
    assert etiqueta("envelope.size.x") == "Dimensión X"
