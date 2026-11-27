"""Normaliza números dictados en español cuando van seguidos de una unidad."""

import re

_BASIC = """
cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince
dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro
veinticinco veintiseis veintisiete veintiocho veintinueve
""".split()
VALUES = {word: value for value, word in enumerate(_BASIC)}
VALUES.update(
    zip("treinta cuarenta cincuenta sesenta setenta ochenta noventa".split(), range(30, 100, 10))
)
VALUES.update(
    zip(
        (
            "cien doscientos trescientos cuatrocientos quinientos "
            "seiscientos setecientos ochocientos novecientos"
        ).split(),
        range(100, 1000, 100),
    )
)
VALUES.update(un=1, una=1, veintiun=21, ciento=100)
_NUMBER = "(?:" + "|".join([*VALUES, "mil"]) + ")"
_UNITS = r"milimetros?|centimetros?|metros?|cm|mm|m|pulgadas?|grados?|pies|bar|kg"
_SPOKEN = re.compile(
    rf"\b(?P<minus>menos\s+)?(?P<words>{_NUMBER}(?:\s+(?:(?:y|coma|punto)\s+)?{_NUMBER})*)"
    rf"\s+(?=(?:{_UNITS})\b)"
)


def _integer(words):
    total = current = 0
    for word in words:
        if word == "mil":
            total += max(current, 1) * 1_000
            current = 0
        elif word != "y":
            current += VALUES[word]
    return total + current


def digits(text):
    def format_value(match):
        words = match["words"].split()
        sign = "-" if match["minus"] else ""
        separators = [i for i, word in enumerate(words) if word in ("coma", "punto")]
        if len(separators) > 1:
            return match[0]
        if not separators:
            return f"{sign}{_integer(words)} "
        index = separators[0]
        rest = words[index + 1 :]
        decimal = (
            "".join(str(VALUES[word]) for word in rest)
            if all(VALUES.get(word, 10) < 10 for word in rest)
            else str(_integer(rest))
        )
        return f"{sign}{_integer(words[:index])},{decimal} "

    return _SPOKEN.sub(format_value, text)
