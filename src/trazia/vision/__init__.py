"""Visión (DEC-03, 04 y 31): proveedores intercambiables, caché, política y mosaicos."""

from .base import (
    PolicyError,
    ProviderResult,
    RespuestaInvalida,
    VisionError,
    VisionProvider,
    VisionUnavailable,
)
from .prompts import TASKS
from .providers import AzureOpenAIProvider, OllamaProvider, get_provider
from .reader import PageReading, read_page, render_page

__all__ = [
    "TASKS",
    "AzureOpenAIProvider",
    "OllamaProvider",
    "PageReading",
    "PolicyError",
    "ProviderResult",
    "RespuestaInvalida",
    "VisionError",
    "VisionProvider",
    "VisionUnavailable",
    "get_provider",
    "read_page",
    "render_page",
]
