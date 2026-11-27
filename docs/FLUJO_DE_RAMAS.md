# Ramas de trabajo del equipo

Cada agente hace los cambios y commits en la rama de la persona a la que asiste.

| Persona | Rama en GitLab |
| --- | --- |
| Javier Saguar Antona | `trabajo/javier` |
| Miguel Vera del Castillo | `trabajo/miguel` |
| Alejandro Cuevas Cid | `trabajo/alejandro` |
| Iria Lozano Carrasco | `trabajo/iria` |

## Antes de empezar

Ejecuta `git fetch origin` y cámbiate a tu rama. Si es la primera vez que la usas,
crea la copia local con seguimiento, por ejemplo `git switch --track origin/trabajo/iria`.
Si la rama ya existe en tu clon, cámbiate a ella y actualízala con `git pull --ff-only`.

## Al terminar una tarea

1. Haz commit en tu rama y ejecuta `git fetch origin` y `git merge origin/main` desde esa rama.
2. Si hay conflictos, resuélvelos en tu rama y vuelve a verificar los cambios. Si la resolución
   requiere una decisión de otro frente, coordínala antes de integrar en `main`.
3. Ejecuta las comprobaciones de [AGENTS.md](../AGENTS.md) que correspondan al cambio. Cuando
   pasen y la rama esté limpia, sube primero tu rama a GitLab. Por ejemplo,
   `git push origin trabajo/iria`.
4. Desde tu rama, integra el commit comprobado con `git push origin HEAD:main`. Git permite
   ese envío solo si `main` puede avanzar hasta el commit sin reescribir su historial.
   Si alguien ha actualizado `main` e impide el envío, vuelve al paso 1 para incorporar esa
   versión y repetir las comprobaciones. Los envíos siempre se hacen sin forzar.
5. Ejecuta `git fetch origin` y comprueba que tu commit está en `origin/main`. Puedes verificarlo
   con `git merge-base --is-ancestor HEAD origin/main`. Indica el hash del commit al cerrar la tarea.
