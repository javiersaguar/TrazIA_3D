"""Planos GA vectoriales y libros de datos vinculados a la geometría sintética."""

from datetime import datetime
from itertools import chain

from make_industrial_designs import hull
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A1, landscape
from reportlab.pdfgen.canvas import Canvas

GA_SIZE = landscape(A1)
PAGE_W, PAGE_H = (measure / 2 for measure in GA_SIZE)
INK = "#151515"
ACCENT = "#242424"
BORDER = "#373737"


def text(pdf, x, y, value, size=10, bold=False):
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawString(x, y, str(value).replace("→", "->"))


def path(pdf, points, *, fill=None, stroke=ACCENT, weight=0.7, closed=False):
    first, *rest = points
    route = pdf.beginPath()
    route.moveTo(*first)
    for p in rest:
        route.lineTo(*p)
    if closed:
        route.close()
    pdf.setLineWidth(weight)
    pdf.setStrokeColor(stroke)
    if fill is not None:
        pdf.setFillColor(fill)
    pdf.drawPath(route, stroke=1, fill=int(fill is not None))


def frame(pdf, project, revision, sheet, title, page):
    """Marco A1 zonificado y cajetín CAD. El identificador y el emisor son ficticios."""
    pdf.scale(2, 2)
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.55)
    left, right, bottom, top = 25, PAGE_W - 23, 25, PAGE_H - 23
    pdf.rect(left, bottom, right - left, top - bottom)
    for i in range(8):
        x = left + (right - left) * i / 8
        pdf.line(x, top, x, top + 5)
        pdf.line(x, bottom, x, bottom - 5)
        text(pdf, x + (right - left) / 16, top + 6, i + 1, 5.5)
    for i, letter in enumerate("ABCDEF"):
        y = top - (top - bottom) * i / 6
        pdf.line(left - 5, y, left, y)
        pdf.line(right, y, right + 5, y)
        text(pdf, 14, y - (top - bottom) / 12, letter, 5.5)
    block_x, block_y = right - 339, bottom
    pdf.rect(block_x, block_y, 339, 61)
    for y in (39, 57, 72):
        pdf.line(block_x, y, right, y)
    pdf.line(right - 54, bottom, right - 54, 57)
    pdf.line(right - 126, bottom, right - 126, 39)
    text(pdf, block_x + 5, 76, "TRAZIA-3D / SYNTHETIC - NOT FOR CONSTRUCTION", 6.2, True)
    text(pdf, block_x + 5, 61, title.upper(), 8, True)
    text(pdf, block_x + 5, 50, "DWG NO. / Nº PLANO", 4.8)
    text(pdf, block_x + 5, 42, f"{project.code}-{sheet}", 7, True)
    text(pdf, right - 49, 43, f"REV. {revision}", 7, True)
    text(pdf, block_x + 5, 30, "A1   |   SCALE AS SHOWN   |   DIMENSIONS IN mm", 6)
    text(pdf, right - 120, 30, f"SHEET {page}", 6, True)
    text(pdf, right - 49, 30, project.setting.upper()[:9], 5.2)
    text(pdf, left, 14, "SYNTHETIC GA / PLANO DE ENSAYO. NO VÁLIDO PARA CONSTRUCCIÓN.", 6)


def ga_canvas(target, title):
    pdf = Canvas(str(target), pagesize=GA_SIZE, invariant=1, pageCompression=1)
    pdf.setTitle(title)
    pdf.setAuthor("TrazIA-3D | Conjunto sintetico")
    return pdf


def view_title(pdf, x, y, label, scale):
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.35)
    pdf.line(x, y - 2, x + pdf.stringWidth(label, "Helvetica-Bold", 9), y - 2)
    text(pdf, x, y, label, 9, True)
    text(pdf, x, y - 13, f"SCALE 1 : {scale:g}" if scale else "N.T.S.", 6.6)


def dimension(pdf, x0, y0, x1, y1, offset, label, *, vertical=False):
    """Líneas auxiliares y flechas cerradas de una cota de CAD."""
    pdf.saveState()
    if vertical:
        pdf.translate(x0, y0)
        pdf.rotate(90)
        x0, y0, x1, y1 = 0, 0, y1 - y0, x0 - x1
    y = y0 + offset
    pdf.setStrokeColor(ACCENT)
    pdf.setFillColor(ACCENT)
    pdf.setLineWidth(0.32)
    overrun = 3 if offset >= 0 else -3
    pdf.line(x0, y0, x0, y + overrun)
    pdf.line(x1, y1, x1, y + overrun)
    pdf.line(x0, y, x1, y)
    left, right = sorted((x0, x1))
    arrow = min(4, (right - left) / 4)
    for end, direction in ((left, 1), (right, -1)):
        path(
            pdf,
            [(end, y), (end + direction * arrow, y - 1.1), (end + direction * arrow, y + 1.1)],
            fill=INK,
            weight=0.2,
            closed=True,
        )
    length = pdf.stringWidth(label, "Helvetica", 7)
    text(pdf, (left + right - length) / 2, y + 2.5, label, 7)
    pdf.restoreState()


def chart(pdf, area, axes, parts, *, line_paths=None, equipment=None, dimensioned=False):
    x, y, width, height = area
    a, b = axes
    drawings = [(part, part.drawing()) for part in parts]
    vertices = [point for _, drawing in drawings for _, mesh in drawing for point in mesh.vertices]
    low_a, high_a = min(v[a] for v in vertices), max(v[a] for v in vertices)
    low_b, high_b = min(v[b] for v in vertices), max(v[b] for v in vertices)
    fitted = min((width - 65) / (high_a - low_a), (height - 53) / (high_b - low_b))
    points_per_m = 1000 * 72 / 25.4 / 2
    min_denominator = points_per_m / fitted
    denominator = next(
        (
            v
            for v in (
                5,
                10,
                15,
                20,
                25,
                30,
                40,
                50,
                75,
                100,
                125,
                150,
                200,
                250,
                300,
                400,
                500,
                750,
                1000,
            )
            if v >= min_denominator
        ),
        int(min_denominator + 1),
    )
    scale = points_per_m / denominator
    ox, oy = (
        x + (width - scale * (high_a - low_a)) / 2,
        y + 24 + (height - 45 - scale * (high_b - low_b)) / 2,
    )

    def xy(pa, pb):
        return ox + (pa - low_a) * scale, oy + (pb - low_b) * scale

    header = "PLANTA / TOP VIEW (X-Y)" if b == 1 else "ALZADO / FRONT VIEW (X-Z)"
    if a == 1:
        header = "PERFIL / END VIEW (Y-Z)"
    view_title(pdf, x + 9, y + height - 11, header, denominator)
    depth = ({0, 1, 2} - {a, b}).pop()
    for part, drawing in sorted(drawings, key=lambda item: item[0].kind != "structure"):
        if part.kind == "pipe":
            continue
        faces = [
            (material, [mesh.vertices[i] for i in face])
            for material, mesh in drawing
            for face in mesh.faces
        ]
        if equipment is not None and part.kind != "structure":
            faces = [
                (material, mesh.vertices[first:last])
                for material, mesh in drawing
                for first, last, _ in mesh.groups
            ]
        for _, points in sorted(
            faces,
            key=lambda entry: sum(v[depth] for v in entry[1]) / len(entry[1]),
            reverse=b == 2 and a == 0,
        ):
            outline = hull((v[a], v[b]) for v in points)
            if len(outline) < 3:
                continue
            path(
                pdf, [xy(*p) for p in outline], fill="#ffffff", stroke=INK, weight=0.24, closed=True
            )
    if line_paths:
        for line, coords in line_paths:
            points = [xy(p[a], p[b]) for p in coords]
            pdf.setDash(5, 1.4)
            path(pdf, points, weight=0.55, stroke=INK)
            pdf.setDash()
            if b == 1:
                mid = tuple((p + q) / 2 for p, q in zip(points[3], points[4]))
                text(pdf, mid[0] - 9, mid[1] + 3, line.tag, 6, True)
    if equipment and b == 1:
        for eq in equipment.values():
            cx, cy = xy(*eq.xy)
            pdf.setFillColor("#ffffff")
            pdf.rect(cx - 13, cy + 4, 30, 9, fill=1, stroke=1)
            text(pdf, cx - 11, cy + 6.5, eq.tag, 6.2, True)
    if not dimensioned:
        return
    left, bottom = xy(low_a, low_b)
    right, top = xy(high_a, high_b)
    # Cotas generales tomadas de los mismos vértices que exporta el IFC.
    if b == 1:
        dimension(pdf, left, bottom, right, bottom, -13, f"{1000 * (high_a - low_a):.0f} O/A")
    dimension(
        pdf, right, bottom, right, top, -14, f"{1000 * (high_b - low_b):.0f} O/A", vertical=True
    )
    if b == 1:
        north_x, north_y = x + 29, y + height - 44
        pdf.line(north_x, north_y - 24, north_x, north_y)
        path(
            pdf,
            [(north_x, north_y), (north_x - 3, north_y - 8), (north_x + 3, north_y - 8)],
            fill=INK,
            weight=0.35,
            closed=True,
        )
        text(pdf, north_x + 7, north_y - 3, "N +Y", 7, True)


def table(pdf, x, top, headers, rows, widths, height=24, *, font=8):
    width = sum(widths)
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.32)
    bottom = top - (len(rows) + 1) * height
    edge = x
    for span in (*widths, 0):
        pdf.line(edge, bottom, edge, top)
        edge += span
    pdf.line(x, top, x + width, top)
    for i, row in enumerate((headers, *rows)):
        y = top - (i + 1) * height
        pdf.setStrokeColor(BORDER)
        pdf.line(x, y, x + width, y)
        left = x
        for j, (value, span) in enumerate(zip(row, widths)):
            text(pdf, left + 4, y + height * 0.33, value, font, i == 0 or j == 0)
            left += span


def changes(project, revision):
    return [
        (
            c.tag,
            c.label,
            f"{c.before:g}",
            f"{c.after:g}",
            c.unit,
            "Aplicado" if revision == "B" else "Base A",
        )
        for c in project.changes
    ]


class ReviewEvidence:
    """Cajas normalizadas al origen superior del PDF, con el mismo tag que el IFC."""

    def __init__(self):
        self.fields = []

    def field(self, tag, key, label, value, unit, page, box):
        x, y, w, h = box
        self.fields.append(
            {
                "path": f"{tag}.{key}" if tag else f"planta.{key}",
                "label": label,
                "elementId": (f"detail:element:{tag}" if "/" in tag else f"element:{tag}")
                if tag
                else "",
                "value": value,
                "unit": unit,
                "page": page,
                "bbox": [
                    round(x / PAGE_W, 6),
                    round(1 - (y + h) / PAGE_H, 6),
                    round((x + w) / PAGE_W, 6),
                    round(1 - y / PAGE_H, 6),
                ],
            }
        )

    def row(self, tag, page, x, top, index, height, widths, fields, first_column):
        for offset, (key, label, value, unit) in enumerate(fields, first_column):
            self.field(
                tag,
                key,
                label,
                value,
                unit,
                page,
                (
                    x + sum(widths[:offset]) + 3,
                    top - height * (index + 2) + 2,
                    widths[offset] - 6,
                    height - 4,
                ),
            )


def extents(low, high):
    return [round(float(b - a), 3) for a, b in zip(low, high)]


def interfaces(lines, paths):
    """Marca local N1, N2… por equipo; las coordenadas son los extremos de puerto IFC."""
    counts = {}
    for tag, line in sorted(lines.items()):
        for owner, sense, point in (
            (line.start, "SALIDA / OUTLET", paths[tag][0]),
            (line.end, "ENTRADA / INLET", paths[tag][-1]),
        ):
            counts[owner] = counts.get(owner, 0) + 1
            yield owner, f"N{counts[owner]}", line, sense, [round(float(n * 1000)) for n in point]


def project_pdf(target, project, revision, equipment, lines, paths, parts):
    components = [
        (f"{part.tag}/{component.key}", component.label, *component.bounds())
        for part in parts
        for component in part.components
    ]
    low = [min(item[2][axis] for item in components) for axis in range(3)]
    high = [max(item[3][axis] for item in components) for axis in range(3)]
    evidence = ReviewEvidence()
    points_per_sheet = 28
    pages = 3 + (len(parts) + len(components) + points_per_sheet - 1) // points_per_sheet
    pdf = ga_canvas(target, f"{project.code} · GA de implantación · Rev {revision}")
    frame(pdf, project, revision, "GA-001", project.name, f"01 / {pages:02}")
    chart(
        pdf,
        (38, 404, 758, 393),
        (0, 1),
        parts,
        line_paths=[(line, paths[tag]) for tag, line in lines.items()],
        equipment=equipment,
        dimensioned=True,
    )
    chart(
        pdf,
        (38, 92, 758, 312),
        (0, 2),
        parts,
        line_paths=[(line, paths[tag]) for tag, line in lines.items()],
        equipment=equipment,
        dimensioned=True,
    )
    pdf.setStrokeColor(BORDER)
    pdf.line(805, 86, 805, PAGE_H - 23)
    fields = [
        (key, label, round(value * 1000), "mm")
        for key, label, value in zip(
            ("x", "y", "z", "piso"),
            ("Largo total X", "Ancho total Y", "Altura total Z", "Cota del piso"),
            [*extents(low, high), project.deck],
        )
    ]
    text(pdf, 824, 784, "DATOS DE DISEÑO / DESIGN DATA", 9, True)
    widths = (228, 99)
    table(
        pdf,
        824,
        773,
        ("DESIGNACIÓN / DESCRIPTION", "DIM. (mm)"),
        [(label.upper(), value) for _, label, value, _ in fields],
        widths,
        16,
    )
    for i, field in enumerate(fields):
        evidence.row("", 1, 824, 773, i, 16, widths, [field], 1)
    text(pdf, 824, 675, "CONJUNTOS / EQUIPMENT LIST", 9, True)
    table(
        pdf,
        824,
        664,
        ("POS.", "DESCRIPTION"),
        [(tag, item.name.upper()) for tag, item in equipment.items()],
        (55, 272),
        15,
    )
    text(pdf, 824, 528, "REFERENCE DRAWINGS / PLANOS DE REFERENCIA", 9, True)
    table(
        pdf,
        824,
        516,
        ("SHEET", "DESCRIPTION"),
        [
            ("02", "EQUIPMENT & PIPING SCHEDULE"),
            ("03", "NOZZLE LIST / PORT COORDINATES"),
            (f"04-{pages:02}", "PARTS LIST & OVERALL DIMENSIONS"),
        ],
        (55, 272),
        15,
    )
    text(pdf, 824, 414, "GENERAL NOTES / NOTAS GENERALES", 9, True)
    notes = (
        "1. ALL DIMENSIONS ARE IN mm UNLESS OTHERWISE SPECIFIED.",
        "2. NORTH +Y; ELEVATIONS FROM LOCAL IFC DATUM.",
        "3. N1, N2... ARE LOCAL IDENTIFIERS WITHIN EACH EQUIPMENT.",
        "4. DRAFT / SYNTHETIC. FOR TRACEABILITY TEST ONLY.",
    )
    for i, note in enumerate(notes):
        text(pdf, 824, 399 - 13 * i, note, 7.2)
    text(pdf, 824, 126, "REVISION RECORD", 8, True)
    table(
        pdf, 824, 115, ("REV.", "DESCRIPTION"), [(revision, "SYNTHETIC TEST ISSUE")], (55, 272), 12
    )
    pdf.showPage()
    frame(pdf, project, revision, "GA-002", "Equipos, interfaces y revisión", f"02 / {pages:02}")
    text(pdf, 48, 744, "LISTA DE EQUIPOS / EQUIPMENT LIST", 9, True)
    equipment_widths = (72, 277, 219, 150, 127, 127, 126)
    table(
        pdf,
        48,
        714,
        (
            "Tag",
            "Equipo",
            "Servicio",
            "X / Y (mm)",
            "LARGO NOMINAL",
            "ANCHO NOMINAL",
            "ALTO NOMINAL",
        ),
        [
            (
                item.tag,
                item.name,
                item.service,
                f"{item.xy[0] * 1000:.0f} / {item.xy[1] * 1000:.0f}",
                *(round(n * 1000) for n in item.size),
            )
            for item in equipment.values()
        ],
        equipment_widths,
        23,
    )
    for i, item in enumerate(equipment.values()):
        fields = [
            (key, f"{item.tag} · {name}", round(value * 1000), "mm")
            for key, name, value in zip(
                ("largo", "ancho", "altura"),
                ("Largo nominal", "Ancho nominal", "Alto nominal"),
                item.size,
            )
        ]
        evidence.row(item.tag, 2, 48, 714, i, 23, equipment_widths, fields, 4)
    line_widths = (95, 115, 115, 213, 111, 449)
    text(pdf, 48, 522, "LISTA DE LÍNEAS / PIPING LIST", 9, True)
    table(
        pdf,
        48,
        512,
        ("Línea", "Desde", "Hasta", "Servicio", "DN (mm)", "COTA DE RACK (mm)"),
        [
            (
                line.tag,
                line.start,
                line.end,
                line.fluid,
                line.dn,
                round((line.rack_z + project.deck) * 1000),
            )
            for line in lines.values()
        ],
        line_widths,
        23,
    )
    for i, line in enumerate(lines.values()):
        evidence.row(
            line.tag,
            2,
            48,
            512,
            i,
            23,
            line_widths,
            (
                ("dn", f"{line.tag} · Diámetro nominal", line.dn, "mm"),
                (
                    "rack",
                    f"{line.tag} · Cota de rack",
                    round((line.rack_z + project.deck) * 1000),
                    "mm",
                ),
            ),
            4,
        )
    text(pdf, 48, 302, "CAMBIOS DE REV. B", 12, True)
    table(
        pdf,
        48,
        285,
        ("Tag", "Modificación", "A", "B", "Unidad", "Estado"),
        changes(project, revision),
        (95, 488, 102, 102, 121, 190),
        26,
    )
    text(pdf, 48, 172, "NORTH +Y | +Z ELEVATION | LOCAL PROCESS DATUM", 8, True)
    text(pdf, 48, 156, "FOR NOZZLE / PORT COORDINATES SEE SHEET 03.", 7)
    pdf.showPage()
    frame(pdf, project, revision, "GA-003", "Conexiones / Nozzle schedule", f"03 / {pages:02}")
    text(pdf, 48, 774, "LISTA DE BOQUILLAS / NOZZLE LIST", 9, True)
    widths = (102, 72, 108, 244, 112, 148, 148, 164)
    ports = list(interfaces(lines, paths))
    table(
        pdf,
        48,
        757,
        ("EQUIPMENT", "POS.", "LINE NO.", "SERVICE", "DN", "X", "Y", "EL. Z"),
        [
            (owner, mark, line.tag, sense, line.dn, *point)
            for owner, mark, line, sense, point in ports
        ],
        widths,
        19,
    )
    for i, (owner, mark, line, _, point) in enumerate(ports):
        evidence.row(
            owner,
            3,
            48,
            757,
            i,
            19,
            widths,
            [
                (f"{mark}.{key}", f"{owner}/{mark} · {label}", value, "mm")
                for key, label, value in zip(
                    ("dn", "x", "y", "z"), ("DN", "X", "Y", "Elevación"), (line.dn, *point)
                )
            ],
            4,
        )
    text(pdf, 48, 420, "NOTES:", 8, True)
    text(pdf, 48, 406, "1. POSITIONS N1, N2, ETC. ARE UNIQUE WITHIN EACH EQUIPMENT TAG.", 7)
    text(
        pdf,
        48,
        392,
        "2. X, Y AND EL. Z LOCATE THE IFC CONNECTION POINT, IN mm FROM PROJECT ORIGIN.",
        7,
    )
    text(pdf, 48, 378, "3. NPS, FLANGE CLASS AND STANDOUT ARE NOT SPECIFIED IN THE PLANT IFC.", 7)
    assemblies = []
    for part in parts:
        children = [item for item in components if item[0].split("/", 1)[0] == part.tag]
        minimum = [min(item[2][axis] for item in children) for axis in range(3)]
        maximum = [max(item[3][axis] for item in children) for axis in range(3)]
        assemblies.append((part.tag, "Conjunto: " + part.name, minimum, maximum))
    catalog = sorted(chain(assemblies, components), key=lambda item: item[0])
    widths = (221, 386, 96, 96, 96, 101, 101)
    for start in range(0, len(catalog), points_per_sheet):
        page = start // points_per_sheet + 4
        rows = catalog[start : start + points_per_sheet]
        pdf.showPage()
        frame(
            pdf,
            project,
            revision,
            f"GA-{page:03}",
            "Despiece y cotas exteriores",
            f"{page:02} / {pages:02}",
        )
        text(
            pdf,
            48,
            713,
            "PARTS LIST / ENVELOPE DIMENSIONS ON IFC AXES. EL. Z REFERRED TO IFC ORIGIN.",
            8,
        )
        rendered = []
        for i, (tag, label, minimum, maximum) in enumerate(rows):
            values = [
                round(float(n * 1000)) for n in (*extents(minimum, maximum), minimum[2], maximum[2])
            ]
            rendered.append((tag, label, *values))
            fields = [
                (key, f"{tag} · {name}", value, "mm")
                for key, name, value in zip(
                    ("x", "y", "z", "zmin", "zmax"),
                    (
                        "Envolvente X",
                        "Envolvente Y",
                        "Envolvente Z",
                        "Cota inferior Z",
                        "Cota superior Z",
                    ),
                    values,
                )
            ]
            evidence.row(tag, page, 48, 691, i, 21, widths, fields, 2)
        table(
            pdf,
            48,
            691,
            ("Tag IFC", "Componente", "X", "Y", "Z", "EL. Z MIN.", "EL. Z MAX."),
            rendered,
            widths,
            21,
        )
    pdf.save()
    return evidence.fields


def equipment_pdf(target, project, revision, eq, part, lines, routes):
    pdf = ga_canvas(target, f"{eq.tag} · GA de equipo · Rev {revision}")
    remaining = part.details[8:]
    pages = 1 + (len(remaining) + 36) // 37
    frame(pdf, project, revision, eq.tag, eq.name, f"01 / {pages:02}")
    text(pdf, 48, 711, f"TAG = {eq.tag}", 13, True)
    text(pdf, 490, 711, f"{eq.service}   |   Cota del piso: {project.deck:g} m", 10)
    chart(pdf, (46, 347, 545, 345), (0, 2), [part])
    chart(pdf, (606, 347, 539, 345), (0, 1), [part])
    text(pdf, 46, 315, "ENVOLVENTE EXTERIOR MEDIDA EN EL IFC", 10, True)
    for index, (label, value, unit) in enumerate(envelope_rows(part)):
        text(pdf, 46, 294 - index * 15, f"{label} = {value:.1f} {unit}", 10)
    own = [line for line in lines.values() if eq.tag in (line.start, line.end)]
    table(
        pdf,
        606,
        324,
        ("Interfaz", "DN (mm)", "X / Y / Z (m)"),
        [
            (
                line.tag,
                line.dn,
                " / ".join(
                    f"{value:.2f}" for value in routes[line.tag][0 if eq.tag == line.start else -1]
                ),
            )
            for line in own
        ],
        (192, 92, 255),
    )
    table(
        pdf,
        46,
        190,
        ("Componente", "Acabado de referencia", "Función"),
        part.details[:8],
        (360, 265, 474),
        height=15,
    )
    for start in range(0, len(remaining), 37):
        pdf.showPage()
        frame(
            pdf,
            project,
            revision,
            eq.tag,
            f"{eq.name} · Despiece",
            f"{start // 37 + 2:02} / {pages:02}",
        )
        table(
            pdf,
            46,
            709,
            ("Componente", "Acabado de referencia", "Función"),
            remaining[start : start + 37],
            (360, 265, 474),
            height=17,
        )
    pdf.save()


def sheet(workbook, name, header, rows, widths):
    ws = workbook.create_sheet(name)
    ws.append(header)
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="18354B")
        cell.alignment = Alignment(wrap_text=True)
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    return ws


def workbook(path_, project, revision, equipment, lines, routes, parts):
    book = Workbook()
    book.remove(book.active)
    date = datetime(2026, 1, 1)
    book.properties.created = book.properties.modified = date
    book.properties.title = f"{project.code} / Rev {revision} / Datos sintéticos"
    sheet(
        book,
        "Proyecto",
        ("Campo", "Valor"),
        (
            ("Procedencia", "Datos sintéticos · DRAFT"),
            ("Proyecto", project.name),
            ("Entorno base", project.setting),
            ("Revisión", revision),
            ("Elevación de piso (m)", project.deck),
            ("Ejes", "+X Este, +Y Norte de dibujo, +Z Elevación"),
            ("Alcance", "Envolventes y conexiones conceptuales"),
        ),
        (30, 74),
    )
    sheet(
        book,
        "Equipos",
        (
            "Tag",
            "Descripción",
            "Familia",
            "Servicio",
            "X (m)",
            "Y (m)",
            "Largo (mm)",
            "Ancho (mm)",
            "Alto (mm)",
            "Plano",
        ),
        [
            (
                eq.tag,
                eq.name,
                eq.family,
                eq.service,
                *eq.xy,
                *(int(round(value * 1000)) for value in eq.size),
                f"GAD_{eq.tag}_rev{revision}.pdf",
            )
            for eq in equipment.values()
        ],
        (15, 43, 22, 29, 12, 12, 16, 16, 16, 28),
    )
    sheet(
        book,
        "Líneas",
        ("Línea", "Origen", "Destino", "Servicio", "DN (mm)", "Rack Y (m)", "Rack Z (m)"),
        [
            (
                line.tag,
                line.start,
                line.end,
                line.fluid,
                line.dn,
                line.rack_y,
                line.rack_z + project.deck,
            )
            for line in lines.values()
        ],
        (18, 18, 18, 20, 18, 18, 18),
    )
    sheet(
        book,
        "Nodos",
        ("Línea", "Punto", "X (m)", "Y (m)", "Z (m)"),
        [
            (tag, i, *(round(axis, 4) for axis in point))
            for tag, route in routes.items()
            for i, point in enumerate(route, 1)
        ],
        (18, 12, 18, 18, 18),
    )
    sheet(
        book,
        "Componentes",
        ("Tag", "Tipo", "Componente", "Acabado", "Función"),
        [(part.tag, part.kind, *detail) for part in parts for detail in part.details],
        (18, 20, 44, 25, 44),
    )
    sheet(
        book,
        "Cambios",
        ("Tag", "Descripción", "Valor A", "Valor B", "Unidad", "Estado"),
        changes(project, revision),
        (18, 72, 18, 18, 14, 18),
    )
    book.save(path_)


def equipment_workbook(path_, project, revision, eq, part, lines, routes):
    book = Workbook()
    book.remove(book.active)
    date = datetime(2026, 1, 1)
    book.properties.created = book.properties.modified = date
    sheet(
        book,
        "Ficha",
        ("Campo", "Valor", "Unidad"),
        (
            ("Procedencia", "Datos sintéticos · DRAFT", "—"),
            ("Proyecto", project.code, "—"),
            ("Tag", eq.tag, None),
            ("Revisión", revision, "—"),
            ("Familia", eq.family, "—"),
            ("Servicio", eq.service, "—"),
            ("X local", eq.xy[0], "m"),
            ("Y local", eq.xy[1], "m"),
            ("Z de piso", project.deck, "m"),
            *(
                (label, round(value * 1000), "mm")
                for label, value in zip(("Largo", "Ancho", "Alto"), eq.size)
            ),
        ),
        (24, 55, 13),
    )
    sheet(
        book,
        "Interfaces",
        ("Línea", "Servicio", "DN (mm)", "X (m)", "Y (m)", "Z (m)"),
        [
            (
                line.tag,
                line.fluid,
                line.dn,
                *(round(axis, 4) for axis in routes[line.tag][0 if eq.tag == line.start else -1]),
            )
            for line in lines.values()
            if eq.tag in (line.start, line.end)
        ],
        (16, 24, 16, 18, 18, 18),
    )
    sheet(book, "Piezas", ("Componente", "Acabado", "Función"), part.details, (44, 24, 44))
    sheet(book, "Envolvente", ("PARAMETER", "VALUE", "UNIT"), envelope_rows(part), (29, 19, 13))
    book.save(path_)


def envelope_rows(part):
    vertices = part.vertices
    for index, axis in enumerate("XYZ"):
        values = [point[index] for point in vertices]
        origin = min(values)
        yield f"ENVELOPE_ORIGIN_{axis}", round(origin * 1000, 1), "mm"
        yield f"ENVELOPE_SIZE_{axis}", round((max(values) - origin) * 1000, 1), "mm"
