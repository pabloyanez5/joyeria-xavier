import pytest

pytest.importorskip("langchain_core")

from app.agente.lc_agente import INSTRUCCIONES  # noqa: E402


def test_las_instrucciones_piden_respuestas_cortas_y_una_pregunta_a_la_vez():
    assert "2 o 3 frases cortas" in INSTRUCCIONES
    assert "una sola pregunta" in INSTRUCCIONES
    assert "no lo repitas" in INSTRUCCIONES


def test_las_instrucciones_fijan_el_orden_de_las_preguntas():
    orden = "tipo de joya, material, ocasión, talla y presupuesto"
    assert orden in INSTRUCCIONES
