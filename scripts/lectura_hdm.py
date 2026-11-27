"""Comando compatible del lector de hojas de datos mecánicos."""

from trazia.lectura.hdm import expand_marks, main, read_hdm

__all__ = ["expand_marks", "read_hdm"]


if __name__ == "__main__":
    main()
