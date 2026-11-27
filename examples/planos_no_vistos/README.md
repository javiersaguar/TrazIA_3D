# Plano de ensayo independiente

`GAD_KO-V-9207_rev0.pdf` es el GA sintético de un separador horizontal con dos silletas,
cinco boquillas de proceso y una boca de hombre. La lámina A1 sigue el tipo de disposición
de los GA del reto: alzado, vista axial, planta, detalles, lista de boquillas y lista
de materiales. Las marcas N1–N5 y M1 se mantienen entre vistas y tabla. La nota N1 define
la proyección radial desde el eje hasta la cara de brida.

El único archivo de entrada es el PDF. La geometría y los valores son sintéticos y la
lámina se identifica como documentación de ensayo.

~~~powershell
uv run trazia lote examples/planos_no_vistos -o generated/plano-no-visto/lectura --tag KO-V-9207 --dataset synthetic --procesos 1
~~~

`uv run python scripts/make_blind_ga.py` reproduce el PDF y deja una verdad de diseño
separada de la carpeta de entrada. En la comprobación inicial, el lector generó un
IFC de la envolvente, recuperó 6/6 tamaños NPS y 6/6 proyecciones radiales, y dejó
las seis conexiones sin colocar en el IFC.
