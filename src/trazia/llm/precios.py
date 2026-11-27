"""Precio por millón de tokens de cada modelo, para el registro y la tabla de coste por nivel.

Los precios de Claude son los de lista de Anthropic en USD, que Microsoft Foundry factura igual.
Los de Azure OpenAI dependen del contrato de la organización y no se suponen: sin precio, la
llamada queda con `coste_conocido = false`.

- `TRAZIA_PRECIO_<MODELO>="entrada,salida"` fija el precio en € por millón de tokens. El nombre
  va en mayúsculas y con `_` en lugar de cualquier otro signo, p. ej. `TRAZIA_PRECIO_GPT_6_1`.
- `TRAZIA_EUR_POR_USD` convierte los precios de lista. Vale 1,0 si no se define: fíjalo antes de
  publicar una cifra.
"""

import os
import re

# USD por millón de tokens (entrada, salida), precios de lista del 03/11/2026.
LISTA_USD = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def _variable(modelo: str) -> str:
    return "TRAZIA_PRECIO_" + re.sub(r"[^A-Z0-9]", "_", modelo.upper())


def precio(modelo: str) -> tuple[float, float] | None:
    """(entrada, salida) en € por millón de tokens, o None si no se conoce."""
    propio = os.environ.get(_variable(modelo), "").strip()
    if propio:
        try:
            entrada, salida = (float(v) for v in propio.split(","))
        except ValueError:
            return None
        return entrada, salida
    if modelo in LISTA_USD:
        try:
            cambio = float(os.environ.get("TRAZIA_EUR_POR_USD", "1.0"))
        except ValueError:
            cambio = 1.0
        entrada, salida = LISTA_USD[modelo]
        return entrada * cambio, salida * cambio
    return None


def coste(modelo: str, tokens_in: int | None, tokens_out: int | None) -> float | None:
    """Coste en € de una llamada, o None si el modelo no tiene precio."""
    tarifa = precio(modelo)
    if tarifa is None:
        return None
    return (tokens_in or 0) / 1e6 * tarifa[0] + (tokens_out or 0) / 1e6 * tarifa[1]
