import pytest

from app.agente.casos_evaluacion import CASOS
from app.agente.intenciones import INTENCIONES, clasificar, clasificar_con_reglas
from app.agente.llm import ErrorLLM, ProveedorLLM


class ModeloFalso(ProveedorLLM):
    def __init__(self, respuesta=None, error=False):
        self.respuesta = respuesta
        self.error = error

    def generar(self, sistema, usuario):
        if self.error:
            raise ErrorLLM("sin red")
        return self.respuesta


def test_el_set_tiene_50_casos_con_intenciones_validas():
    assert len(CASOS) == 50
    assert {esperada for _, esperada in CASOS} <= set(INTENCIONES)


def test_reglas_superan_el_85_por_ciento_en_el_set_de_50():
    aciertos = sum(clasificar_con_reglas(t) == esperada for t, esperada in CASOS)
    assert aciertos / len(CASOS) >= 0.85


@pytest.mark.parametrize(
    "texto, esperada",
    [
        ("Hola, ¿cuánto cuesta un anillo?", "cotizar"),
        ("Gracias, quiero hablar con un asesor", "asesor"),
        ("HOLA!!!", "saludo"),
        ("", "otro"),
    ],
)
def test_prioridad_de_las_reglas(texto, esperada):
    assert clasificar_con_reglas(texto) == esperada


def test_con_modelo_usa_la_etiqueta_que_devuelve():
    assert clasificar("lo que sea", ModeloFalso(" Cotizar.\n")) == "cotizar"


def test_si_el_modelo_responde_algo_raro_usa_las_reglas():
    assert clasificar("Hola", ModeloFalso("banana")) == "saludo"


def test_si_el_modelo_falla_usa_las_reglas():
    assert clasificar("Hola", ModeloFalso(error=True)) == "saludo"
