# TrazIA-3D

Producto del reto GA2MODEL de IndesIAhack 2026. El código Python vive en `src/trazia`.

- Instalar con `uv sync --frozen --extra dev --extra ocr --extra geo --extra api`.
- Verificar con `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q` y `uv run python scripts/guardian_datos.py --todo`.
- El dataset de Técnicas Reunidas vive en `data/` y se puede leer localmente. Sus documentos, IFC y salidas, y cualquier clave, quedan fuera de Git. Las salidas locales van en `generated/`.
- Los ejemplos públicos son sintéticos. Conservar su etiquetado y distinguirlos de las mediciones del evento.
- Mantener valor, unidad, fuente y confianza por campo. Conservar GUID por ID estable.
- La salida automática es DRAFT. Para exportar aprobado se requieren revisión humana, verificación de originales y aprobación vinculada a la huella de los datos. Cualquier modificación de los datos invalida la aprobación anterior.
- El visor lee la geometría del IFC.
- La portada pública carga el IFC sintético del recipiente V-101.
- Hay dos pitches: el final de 3 minutos para el jurado en `pitch/concurso` y el del track, de 5 minutos para los ingenieros de TR, en `pitch/track`. Cuál usar, dónde salen el `.pptx` y el guion y cómo regenerarlos está en [pitch/README.md](pitch/README.md).

## Autoría y publicación

- Commits sin `Co-authored-by` ni firmas de herramientas o asistentes en mensajes, PR, código o documentación.
- Cada agente trabaja y hace commit en la rama de su persona. La asignación y los pasos de publicación están en [Ramas de trabajo del equipo](docs/FLUJO_DE_RAMAS.md).
- Al terminar la tarea, incorpora `origin/main` a tu rama. Integra en `main` cuando el resultado esté libre de conflictos y pase las comprobaciones, siempre sin forzar. Confirma que el commit publicado está en `origin/main` e indica su hash.
