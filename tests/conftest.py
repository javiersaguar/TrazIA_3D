"""Configuración común de las pruebas."""

import os

os.environ.setdefault("TRAZIA_WARMUP", "0")

import pytest

# Pruebas de la API completa de trazia-3d. La API del evento (IB2, Iria) quita voz, aprendizaje,
# /estudio y cuentas, y aún no ha vuelto a conectar el copiloto ni las propuestas de cambio.
# Se marcan xfail no estricto: las que pasan siguen contando. Quitar un archivo de esta lista
# cuando su función vuelva a la API.
API_COMPLETA = {
    "test_accounts_catalogue.py",
    "test_api_base.py",
    "test_api_copilot.py",
    "test_api_copilot_voice.py",
    "test_api_corrections.py",
    "test_api_few_shot.py",
    "test_api_job_cache.py",
    "test_api_learning.py",
    "test_api_offline.py",
    "test_api_review_session.py",
    "test_api_study_jobs.py",
    "test_copilot_cloud.py",
    "test_edicion_asistida.py",
    "test_k8_modelado.py",
    "test_plataforma_cache_fusion.py",
    "test_plataforma_feedback.py",
}


def pytest_collection_modifyitems(items):
    marca = pytest.mark.xfail(reason="API completa de trazia-3d, fuera de la API del evento (IB2)")
    for item in items:
        if item.path.name in API_COMPLETA:
            item.add_marker(marca)
