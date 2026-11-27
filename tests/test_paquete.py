"""Comprueba la instalación del paquete en el primer commit."""

import trazia


def test_paquete_instalado():
    assert trazia.__doc__ and "TrazIA-3D" in trazia.__doc__
