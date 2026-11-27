import math


def derived_field(value, unit, rule, explanation, reading, *dependencies):
    states = {field["state"] for field in (reading, *dependencies)}
    state = next((s for s in ("abstained", "conflict", "assumed") if s in states), "candidate")
    return {
        "value": value,
        "unit": unit,
        "source": {**reading["source"], "rule": rule},
        "state": state,
        "explanation": " ".join(filter(None, (reading["explanation"], explanation))),
    }


def outer_diameter(diameter, attributes, family):
    basis = attributes.get("diameter_basis")
    if basis is None or basis["value"] == "outside":
        return diameter
    if basis["value"] != "inside":
        raise ValueError("El diámetro requiere una referencia interior o exterior")
    thickness = attributes.get("shell_thickness")
    if thickness is None:
        # Sin espesor leído se modela con el diámetro interior: la pieza queda como supuesta
        # y la revisión tiene que aportar el espesor. El error es de dos espesores en diámetro.
        return {
            **derived_field(
                diameter["value"],
                diameter["unit"],
                f"{family}.diametro_interior_sin_espesor",
                "Falta el espesor de virola: se modela con el diámetro interior.",
                diameter,
                basis,
            ),
            "state": "assumed",
        }
    if any(
        field["unit"] != "mm" or not isinstance(field["value"], int | float) or field["value"] <= 0
        for field in (diameter, thickness)
    ):
        raise ValueError("El diámetro interior y el espesor de virola deben ser positivos en mm")
    return derived_field(
        diameter["value"] + 2 * thickness["value"],
        "mm",
        f"{family}.diametro_exterior",
        "Diámetro interior más dos veces el espesor de virola.",
        diameter,
        thickness,
        basis,
    )


def head_mesh(radius: float, depth: float, z: float, up: int, segments=64, rings=12):
    """Semielipsoide macizo cerrado; aproximación de la envolvente exterior en metros."""
    vertices, triangles = [], []
    for row in range(rings):
        angle = math.pi * row / (2 * rings)
        r = radius * math.cos(angle)
        for col in range(segments):
            theta = 2 * math.pi * col / segments
            vertices.append(
                (r * math.cos(theta), r * math.sin(theta), z + up * depth * math.sin(angle))
            )
    pole = len(vertices) + 1
    vertices.append((0.0, 0.0, z + up * depth))
    center = len(vertices) + 1
    vertices.append((0.0, 0.0, z))
    for row in range(rings - 1):
        for col in range(segments):
            a = row * segments + col + 1
            b = row * segments + (col + 1) % segments + 1
            triangles.extend(((a, b, b + segments), (a, b + segments, a + segments)))
    for col in range(segments):
        nxt = (col + 1) % segments
        triangles.append(((rings - 1) * segments + col + 1, (rings - 1) * segments + nxt + 1, pole))
        triangles.append((center, nxt + 1, col + 1))
    if up < 0:
        triangles = [tuple(reversed(t)) for t in triangles]
    return vertices, triangles
