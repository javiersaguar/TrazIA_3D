"""Familias en mm; únicamente los sólidos de salida se expresan en metros."""

import math
from dataclasses import dataclass, field, replace

from ..model import Equipment, Vector3
from .geometry import head_mesh
from .horizontal import saddle_profile_dimensions


@dataclass(frozen=True)
class Solid:
    kind: str
    origin: tuple = (0.0, 0.0, 0.0)
    direction: tuple = (0.0, 0.0, 1.0)
    diameter: float = 0.0
    length: float = 0.0
    thickness: float | None = None
    size: tuple = ()
    points: tuple = ()
    vertices: list = field(default_factory=list)
    triangles: list = field(default_factory=list)
    holes: tuple = ()
    cutouts: tuple = ()


@dataclass(frozen=True)
class Part:
    id: str
    guid_key: str
    solids: tuple[Solid, ...]
    ifc_class: str = "IfcBuildingElementProxy"
    object_type: str = "COMPONENT"
    parent_id: str | None = None
    properties: dict = field(default_factory=dict)
    predefined_type: str | None = None
    classification: tuple = ()
    # Nombre legible de la pieza tal como se lee en el plano; va a IfcRoot.Description.
    description: str | None = None


def vector(value: Vector3):
    return tuple(getattr(value, axis).value / 1000 for axis in "xyz")


AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


# Ejes transversales de cada eje, en orden cíclico (eje, u, v) a derechas.
CROSS = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}


def _place(k: int, a: float, cross: tuple[int, int], u: float, v: float) -> tuple:
    p = [0.0, 0.0, 0.0]
    p[k], p[cross[0]], p[cross[1]] = a, u, v
    return tuple(p)


def _outward(vertices: list, triangles: list) -> list:
    """Da la vuelta a todas las caras si el volumen con signo sale negativo."""
    volume = 0.0
    for i, j, k in triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (vertices[n - 1] for n in (i, j, k))
        volume += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return triangles if volume >= 0 else [(i, k, j) for i, j, k in triangles]


def revolve_mesh(profile, axis: str, center: tuple[float, float], segments=48) -> Solid:
    """Sólido de revolución de un perfil [(a, r)] en mm; sale en metros y cerrado."""
    k, cross = "xyz".index(axis), CROSS[axis]
    puntos = [(a / 1000, r / 1000) for a, r in profile]
    vertices, anillos = [], []
    for a, r in puntos:
        if r <= 0:
            vertices.append(_place(k, a, cross, *center))
            anillos.append([len(vertices)] * segments)
            continue
        inicio = len(vertices)
        for s in range(segments):
            t = 2 * math.pi * s / segments
            vertices.append(
                _place(k, a, cross, center[0] + r * math.cos(t), center[1] + r * math.sin(t))
            )
        anillos.append(list(range(inicio + 1, inicio + segments + 1)))
    triangles = []
    for anillo, siguiente in zip(anillos, anillos[1:]):
        for s in range(segments):
            a, b = anillo[s], anillo[(s + 1) % segments]
            c, d = siguiente[s], siguiente[(s + 1) % segments]
            if a != b:
                triangles.append((a, c, b))
            if c != d:
                triangles.append((b, c, d))
    for (a, r), anillo, sentido in ((puntos[0], anillos[0], 1), (puntos[-1], anillos[-1], -1)):
        if r > 0:
            vertices.append(_place(k, a, cross, *center))
            centro = len(vertices)
            for s in range(segments):
                b, c = anillo[s], anillo[(s + 1) % segments]
                triangles.append((centro, b, c) if sentido > 0 else (centro, c, b))
    return Solid("mesh", vertices=vertices, triangles=_outward(vertices, triangles))


def _ears(poly: list) -> list:
    """Triangula un polígono simple por recorte de orejas; índices desde 0."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))
    idx = list(range(len(poly))) if area > 0 else list(range(len(poly)))[::-1]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    out, guard = [], 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for n in range(len(idx)):
            i, j, k = idx[n - 1], idx[n], idx[(n + 1) % len(idx)]
            a, b, c = poly[i], poly[j], poly[k]
            if cross(a, b, c) <= 1e-12:
                continue
            if any(inside(poly[m], a, b, c) for m in idx if m not in (i, j, k)):
                continue
            out.append((i, j, k))
            idx.pop(n)
            break
        else:
            raise ValueError("Polígono no simple: no se puede triangular")
    out.append(tuple(idx))
    return out


def extrude_mesh(profile, axis: str, start: float, end: float) -> Solid:
    """Prisma de un polígono [(u, v)] en mm (ejes transversales en orden xyz) entre start y end."""
    k = "xyz".index(axis)
    otros = [i for i in range(3) if i != k]
    poly = []
    for u, v in profile:
        p = (u / 1000, v / 1000)
        if not poly or p != poly[-1]:
            poly.append(p)
    if poly[0] == poly[-1]:
        poly.pop()
    # Las tapas salen en sentido antihorario: los laterales tienen que seguir el mismo sentido.
    if sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])) < 0:
        poly.reverse()
    n = len(poly)

    def punto(a, u, v):
        p = [0.0, 0.0, 0.0]
        p[k], p[otros[0]], p[otros[1]] = a, u, v
        return tuple(p)

    vertices = [punto(start / 1000, u, v) for u, v in poly] + [
        punto(end / 1000, u, v) for u, v in poly
    ]
    triangles = []
    for i, j, m in _ears(poly):
        triangles.append((i + 1, m + 1, j + 1))
        triangles.append((n + i + 1, n + j + 1, n + m + 1))
    for i in range(n):
        j = (i + 1) % n
        triangles += [(i + 1, j + 1, n + j + 1), (i + 1, n + j + 1, n + i + 1)]
    return Solid("mesh", vertices=vertices, triangles=_outward(vertices, triangles))


def skid_solid(pieza) -> Solid:
    """Sólido de una pieza de bancada: caja, cilindro, revolución o extrusión (mm → m)."""
    origin, size = vector(pieza.envelope.origin), vector(pieza.envelope.size)
    if pieza.shape in ("revolve", "extrude"):
        k = "xyz".index(pieza.axis)
        if pieza.shape == "revolve":
            centro = tuple(origin[i] + size[i] / 2 for i in CROSS[pieza.axis])
            return revolve_mesh(pieza.profile, pieza.axis, centro)
        return extrude_mesh(
            pieza.profile, pieza.axis, origin[k] * 1000, (origin[k] + size[k]) * 1000
        )
    if pieza.shape != "cylinder":
        return Solid("box", origin=origin, size=size)
    k = "xyz".index(pieza.axis)
    across = [size[i] for i in range(3) if i != k]
    base = [origin[i] + size[i] / 2 for i in range(3)]
    base[k] = origin[k]
    return Solid(
        "cylinder",
        origin=tuple(base),
        direction=AXES[pieza.axis],
        diameter=min(across) * 1000,
        length=size[k] * 1000,
    )


def frustum(bottom: float, top: float, height: float, z: float, segments=64):
    """Malla cerrada y orientada; radios y alturas en metros, sin caras degeneradas."""
    vertices = [
        (
            bottom * math.cos(2 * math.pi * i / segments),
            bottom * math.sin(2 * math.pi * i / segments),
            z,
        )
        for i in range(segments)
    ]
    triangles = []
    if top > 0:
        vertices += [
            (
                top * math.cos(2 * math.pi * i / segments),
                top * math.sin(2 * math.pi * i / segments),
                z + height,
            )
            for i in range(segments)
        ]
        for i in range(segments):
            j = (i + 1) % segments
            triangles.extend(
                [(i + 1, j + 1, j + segments + 1), (i + 1, j + segments + 1, i + segments + 1)]
            )
        cap = len(vertices) + 1
        vertices.append((0.0, 0.0, z + height))
        triangles += [
            (cap, i + segments + 1, (i + 1) % segments + segments + 1) for i in range(segments)
        ]
    else:
        cap = len(vertices) + 1
        vertices.append((0.0, 0.0, z + height))
        triangles += [(i + 1, (i + 1) % segments + 1, cap) for i in range(segments)]
    cap = len(vertices) + 1
    vertices.append((0.0, 0.0, z))
    triangles += [(cap, (i + 1) % segments + 1, i + 1) for i in range(segments)]
    return Solid("mesh", vertices=vertices, triangles=triangles)


def skirt_mesh(base, top, height, thickness, segments=64):
    """Faldón troncocónico hueco, cerrado por el espesor en los dos bordes."""
    vertices = [
        (r * math.cos(a), r * math.sin(a), z)
        for r, z in ((base, 0.0), (top, height), (top - thickness, height), (base - thickness, 0.0))
        for a in (math.tau * i / segments for i in range(segments))
    ]
    triangles = []
    for ring in range(4):
        lower, upper = ring * segments, (ring + 1) % 4 * segments
        for i in range(segments):
            j = (i + 1) % segments
            triangles.extend(
                [
                    (lower + i + 1, lower + j + 1, upper + j + 1),
                    (lower + i + 1, upper + j + 1, upper + i + 1),
                ]
            )
    return Solid("mesh", vertices=vertices, triangles=triangles)


def nozzle_frame(equipment, nozzle):
    if nozzle.position is not None:
        origin = vector(nozzle.position)
        direction = tuple(getattr(nozzle.direction, a).value for a in "xyz")
        norm = math.sqrt(sum(d * d for d in direction))
        return origin, tuple(d / norm for d in direction)
    angle = math.radians(nozzle.azimuth.value)
    direction = (math.cos(angle), math.sin(angle), 0.0)
    radius = equipment.diameter.value / 2000
    return (radius * direction[0], radius * direction[1], nozzle.elevation.value / 1000), direction


def _leg_parts(equipment: Equipment) -> list[Part]:
    legs = equipment.legs
    count = legs.count.value
    azimuths = (
        [angle.value for angle in legs.azimuths]
        if legs.azimuths is not None
        else [360 * index / count for index in range(count)]
    )
    diameter = equipment.diameter.value
    proxy_diameter = min(diameter / 10, diameter / (2 * count))
    radius = (diameter / 2 - proxy_diameter / 4) / 1000
    result = []
    for index, azimuth in enumerate(azimuths, start=1):
        angle = math.radians(azimuth)
        properties = {
            "Estado": "assumed",
            "Regla": "patas.seccion_circular_lod1",
            "AzimutDeg": azimuth,
            "AzimutSupuesto": legs.azimuths is None,
            "RequiereVerificacion": True,
        }
        if legs.section is not None:
            properties["PerfilDeclarado"] = str(legs.section.value)
        result.append(
            Part(
                f"leg-{index}",
                f"leg/{index}",
                (
                    Solid(
                        "cylinder",
                        origin=(radius * math.cos(angle), radius * math.sin(angle), 0.0),
                        diameter=proxy_diameter,
                        length=legs.height.value,
                    ),
                ),
                object_type="LEG_SUPPORT",
                parent_id="shell",
                properties=properties,
            )
        )
    return result


def parts(equipment: Equipment) -> list[Part]:
    if equipment.lod >= 2:
        support = equipment.effective_support
        if (
            equipment.kind == "vertical_vessel"
            and support == "skirt"
            and (equipment.skirt_thickness is None)
        ):
            raise ValueError("El IFC del faldón requiere skirt_thickness con fuente trazable")
    result = []

    def add(
        identifier, solid, key=None, ifc_class="IfcBuildingElementProxy", kind="COMPONENT", trace=()
    ):
        assumed = sorted(
            {field.source.rule for field in trace if field is not None and field.state == "assumed"}
        )
        properties = (
            {"Estado": "assumed", "Regla": ", ".join(assumed), "RequiereVerificacion": True}
            if assumed
            else {}
        )
        result.append(
            Part(identifier, key or identifier, (solid,), ifc_class, kind, properties=properties)
        )

    if equipment.lod == 1:
        piezas = equipment.components or []
        cuerpo = next((pieza for pieza in piezas if pieza.id == "maquina"), None)
        caja = cuerpo.envelope if cuerpo is not None else equipment.envelope
        add(
            "shell",
            skid_solid(cuerpo)
            if cuerpo is not None
            else Solid("box", origin=vector(caja.origin), size=vector(caja.size)),
        )
        if cuerpo is not None:
            result[-1] = replace(result[-1], description=cuerpo.name.value)
        for pieza in piezas:
            if pieza.id == "maquina":
                continue
            add(
                pieza.id,
                skid_solid(pieza),
                key=f"component/{pieza.id}",
                ifc_class=pieza.ifc_class or "IfcBuildingElementProxy",
                kind=pieza.object_type or pieza.id.upper(),
            )
            result[-1] = replace(
                result[-1],
                predefined_type=pieza.predefined_type,
                classification=tuple(pieza.classification or ()),
                description=pieza.name.value,
            )
    elif equipment.kind == "vertical_vessel":
        add(
            "shell",
            Solid(
                "cylinder",
                diameter=equipment.diameter.value,
                length=equipment.height.value,
                origin=(0.0, 0.0, equipment.shell_bottom / 1000),
            ),
            trace=(equipment.diameter, equipment.height),
        )
        for name, up, z in (
            ("bottom_head", -1, equipment.shell_bottom),
            ("top_head", 1, equipment.shell_bottom + equipment.height.value),
        ):
            vertices, triangles = head_mesh(
                equipment.diameter.value / 2000, equipment.head_depth.value / 1000, z / 1000, up
            )
            add(
                name,
                Solid("mesh", vertices=vertices, triangles=triangles),
                kind="ELLIPSOIDAL_HEAD",
                trace=(equipment.diameter, equipment.head_depth),
            )
        if equipment.effective_support == "legs":
            result.extend(_leg_parts(equipment))
        else:
            add(
                "skirt",
                Solid(
                    "cylinder",
                    diameter=equipment.diameter.value,
                    length=equipment.skirt_height.value,
                    thickness=equipment.skirt_thickness.value,
                ),
                kind="SKIRT_SUPPORT",
                trace=(equipment.diameter, equipment.skirt_height, equipment.skirt_thickness),
            )
    elif equipment.kind == "horizontal_vessel":
        p = equipment.horizontal
        radius = p.diameter.value / 2000
        center = p.support_height.value / 1000 + radius
        add(
            "shell",
            Solid(
                "cylinder",
                origin=(0.0, 0.0, center),
                direction=(1.0, 0.0, 0.0),
                diameter=p.diameter.value,
                length=p.length.value,
            ),
            trace=(p.diameter, p.length, p.support_height),
        )
        for name, up, x in (("bottom_head", -1, 0.0), ("top_head", 1, p.length.value / 1000)):
            verts, triangles = head_mesh(radius, p.head_depth.value / 1000, 0.0, up)
            # Rotación propia Z→X (det=+1), misma superficie semielipsoidal.
            vertices = [(x + z, y, center - vx) for vx, y, z in verts]
            add(
                name,
                Solid("mesh", vertices=vertices, triangles=triangles),
                kind="ELLIPSOIDAL_HEAD",
                trace=(p.diameter, p.head_depth),
            )
        for i, position in enumerate(p.saddle_positions):
            # Sección con asiento cóncavo en el plano YZ, extruida en X.
            half = p.saddle_span.value / 2000
            width, base = saddle_profile_dimensions(equipment, i + 1)
            base_half = base.value / 2000
            points = [(-base_half, 0.0), (base_half, 0.0)]
            for j in range(25):
                y = half - 2 * half * j / 24
                points.append((y, center - math.sqrt(radius * radius - y * y)))
            add(
                f"saddle-{i + 1}",
                Solid(
                    "profile",
                    origin=(position.value / 1000 - width.value / 2000, 0.0, 0.0),
                    direction=(1.0, 0.0, 0.0),
                    points=tuple(points),
                    length=width.value,
                ),
                kind="SADDLE_SUPPORT",
                trace=(
                    position,
                    width,
                    p.saddle_span,
                    p.support_height,
                    None if base is p.saddle_span else base,
                ),
            )
    elif equipment.kind == "column":
        z = equipment.shell_bottom / 1000
        section_heights = [equipment.skirt_height]
        for index, section in enumerate(equipment.column.sections):
            top = (section.top_diameter or section.diameter).value
            solid = Solid(
                "cylinder",
                diameter=section.diameter.value,
                length=section.height.value,
                origin=(0.0, 0.0, z),
            )
            if top != section.diameter.value:
                solid = frustum(
                    section.diameter.value / 2000, top / 2000, section.height.value / 1000, z
                )
            section_heights.append(section.height)
            add(
                "shell" if index == 0 else f"section-{section.id}",
                solid,
                key=f"section/{section.id}",
                kind="COLUMN_SECTION",
                trace=(*section_heights, section.diameter, section.top_diameter),
            )
            z += section.height.value / 1000
        first, last = equipment.column.sections[0], equipment.column.sections[-1]
        for side, up, elevation, diameter in (
            ("bottom", -1, equipment.shell_bottom / 1000, first.diameter),
            ("top", 1, z, last.top_diameter or last.diameter),
        ):
            depth = equipment.attributes.get(f"column_head_depth_{side}")
            if depth is not None and depth.state != "abstained":
                vertices, triangles = head_mesh(
                    diameter.value / 2000, depth.value / 1000, elevation, up
                )
                add(
                    f"{side}_head",
                    Solid("mesh", vertices=vertices, triangles=triangles),
                    kind="ELLIPSOIDAL_HEAD",
                    trace=(diameter, depth),
                )
        if equipment.effective_support == "skirt":
            skirt = equipment.attributes.get("skirt_diameter")
            thickness = equipment.skirt_thickness
            if (
                skirt is None
                or skirt.state == "abstained"
                or skirt.unit != "mm"
                or not isinstance(skirt.value, int | float)
                or thickness is None
                or thickness.state == "abstained"
                or not 0 < thickness.value < skirt.value / 2
            ):
                raise ValueError("El faldón de columna requiere diámetro y espesor trazados en mm")
            top = equipment.attributes.get("skirt_top_diameter")
            if top is not None and top.state != "abstained":
                if not (
                    top.unit == "mm"
                    and isinstance(top.value, int | float)
                    and top.value > 2 * thickness.value
                ):
                    raise ValueError("El diámetro superior del faldón debe ser trazable en mm")
                solid = skirt_mesh(
                    skirt.value / 2000,
                    top.value / 2000,
                    equipment.shell_bottom / 1000,
                    thickness.value / 1000,
                )
            else:
                solid = Solid(
                    "cylinder",
                    diameter=skirt.value,
                    length=equipment.shell_bottom,
                    thickness=thickness.value,
                )
            add(
                "skirt",
                solid,
                kind="SKIRT_SUPPORT",
                trace=(skirt, top, thickness, equipment.skirt_height),
            )
    elif equipment.kind == "tank":
        p = equipment.tank
        add(
            "shell",
            Solid("cylinder", diameter=p.diameter.value, length=p.height.value),
            trace=(p.diameter, p.height),
        )
        roof_trace = (p.diameter, p.height, p.roof_height, p.roof_evidence)
        if p.roof == "conical":
            add(
                "roof",
                frustum(
                    p.diameter.value / 2000, 0, p.roof_height.value / 1000, p.height.value / 1000
                ),
                kind="ROOF",
                trace=roof_trace,
            )
        elif p.roof == "domed":
            verts, triangles = head_mesh(
                p.diameter.value / 2000, p.roof_height.value / 1000, p.height.value / 1000, 1
            )
            add(
                "roof",
                Solid("mesh", vertices=verts, triangles=triangles),
                kind="ROOF",
                trace=roof_trace,
            )
    for nozzle in equipment.nozzles:
        origin, direction = nozzle_frame(equipment, nozzle)
        add(
            nozzle.id,
            Solid(
                "cylinder",
                diameter=nozzle.diameter.value,
                length=nozzle.projection.value,
                origin=origin,
                direction=direction,
            ),
            key=f"nozzle/{nozzle.stable_id or nozzle.id}",
            ifc_class="IfcPipeSegment",
            kind="NOZZLE",
        )
        if equipment.lod == 3 and nozzle.flange:
            flange = nozzle.flange
            distance = (nozzle.projection.value - flange.thickness.value) / 1000
            add(
                f"{nozzle.id}/flange",
                Solid(
                    "cylinder",
                    diameter=flange.outer_diameter.value,
                    length=flange.thickness.value,
                    thickness=(flange.outer_diameter.value - nozzle.diameter.value) / 2,
                    origin=tuple(a + distance * b for a, b in zip(origin, direction)),
                    direction=direction,
                ),
                key=f"nozzle/{nozzle.stable_id or nozzle.id}/flange",
                ifc_class="IfcPipeFitting",
                kind="FLANGE",
            )
    if equipment.lod == 3:
        for platform in equipment.platforms:
            add(
                f"platform-{platform.id}",
                Solid("box", origin=vector(platform.origin), size=vector(platform.size)),
                key=f"platform/{platform.id}",
                kind="PLATFORM",
            )
        for ladder in equipment.ladders:
            x, y, z = vector(ladder.origin)
            width = ladder.width.value / 1000
            solids = [
                Solid(
                    "cylinder",
                    origin=(x + offset, y, z),
                    diameter=ladder.rail_diameter.value,
                    length=ladder.height.value,
                )
                for offset in (0, width)
            ]
            for i in range(1, int(ladder.height.value / ladder.rung_spacing.value) + 1):
                solids.append(
                    Solid(
                        "cylinder",
                        origin=(x, y, z + i * ladder.rung_spacing.value / 1000),
                        direction=(1.0, 0.0, 0.0),
                        diameter=ladder.rail_diameter.value,
                        length=ladder.width.value,
                    )
                )
            result.append(
                Part(
                    f"ladder-{ladder.id}",
                    f"ladder/{ladder.id}",
                    tuple(solids),
                    object_type="LADDER",
                )
            )
    return result
