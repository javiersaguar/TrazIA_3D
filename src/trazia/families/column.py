"""Ensamblado de virolas de columna en el orden citado por el plano."""

import re


def sections_from_candidates(values, *, preview_abstentions=False):
    sections = {}
    for path, field in values.items():
        match = re.fullmatch(
            r"column\.sections\.([A-Za-z0-9_-]+)\.(order|diameter|top_diameter|height)", path
        )
        if match:
            section_id, key = match.groups()
            sections.setdefault(section_id, {"id": section_id})[key] = field
    if not sections:
        return None

    ordered = {}
    for section_id, section in sections.items():
        order = section.get("order")
        if order is None and len(sections) == 1:
            position = 1
        elif (
            order is not None
            and order["state"] != "conflict"
            and (preview_abstentions or order["state"] != "abstained")
            and order["unit"] == "1"
            and isinstance(order["value"], int | float)
            and 1 <= order["value"] <= len(sections)
            and float(order["value"]).is_integer()
        ):
            position = int(order["value"])
            section["order"] = {**order, "value": position}
        else:
            return None
        if position in ordered:
            return None

        if "height" not in section:
            height = values.get(f"shell.courses.{section_id}.height")
            if height is not None:
                section["height"] = height
        if not {"diameter", "height"} <= section.keys():
            return None
        if not preview_abstentions and any(
            field["state"] == "abstained" for key, field in section.items() if key != "id"
        ):
            return None
        ordered[position] = section

    return [ordered[position] for position in range(1, len(ordered) + 1)]
