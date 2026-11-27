"""La consulta en bloque al rtree da lo mismo que rtree y no depende de la versión de numpy."""

import numpy as np
import trimesh

from trazia.families.metrics import _distance_to_surface, _intersection_v


def test_interseccion_igual_que_rtree_con_ampliacion_del_bufer():
    malla = trimesh.creation.icosphere(subdivisions=4)
    puntos = np.random.default_rng(1).uniform(-1.2, 1.2, (800, 3))
    alcance = np.full((len(puntos), 1), 0.4)  # muchas cajas por punto: obliga a ampliar
    ids, cuentas = _intersection_v(malla.triangles_tree, puntos - alcance, puntos + alcance)
    esperado_ids, esperado_cuentas = malla.triangles_tree.intersection_v(
        puntos - alcance, puntos + alcance
    )
    assert int(cuentas.sum()) > 2 * len(puntos)
    assert np.array_equal(ids, esperado_ids) and np.array_equal(cuentas, esperado_cuentas)


def test_distancia_a_la_superficie_igual_que_trimesh():
    malla = trimesh.creation.icosphere(subdivisions=3)
    puntos = np.random.default_rng(2).uniform(-1.5, 1.5, (300, 3))
    esperado = trimesh.proximity.closest_point(malla, puntos)[1]
    assert np.allclose(_distance_to_surface(malla, puntos), esperado)
