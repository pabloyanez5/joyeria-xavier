"""JOY-76: el evaluador del agente real (con herramientas) funciona y no toca la base real."""
import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage  # noqa: E402

from app.agente.casos_evaluacion import CASOS  # noqa: E402
from app.agente.evaluar import ACCION_ESPERADA, accion_del_agente, evaluar_agente, mostrar_agente  # noqa: E402
from tests.test_agente_langchain import llamada, modelo  # noqa: E402


@pytest.mark.parametrize(
    "herramientas, escalar, accion",
    [
        ([], False, "conversar"),
        (["consultar_catalogo"], False, "catalogo"),
        (["mostrar_opciones", "guardar_preferencias"], False, "catalogo"),
        (["consultar_orden"], False, "consultar_orden"),
        (["informacion_joyeria"], False, "informacion"),
        (["derivar_a_asesor"], True, "asesor"),
        (["consultar_catalogo"], True, "asesor"),  # derivar pesa más
    ],
)
def test_que_accion_tomo_el_agente(herramientas, escalar, accion):
    assert accion_del_agente(herramientas, escalar) == accion


def test_todas_las_intenciones_de_los_casos_tienen_accion_esperada():
    assert {esperada for _, esperada in CASOS} <= set(ACCION_ESPERADA)
    assert len(CASOS) == 50


def test_evalua_cada_caso_con_el_agente_real(capsys):
    m = modelo(
        llamada("consultar_orden"),
        AIMessage("Tu orden OP-000001 está en producción."),
        AIMessage("¡Hola, Ana! ¿Qué joya buscas?"),
        llamada("derivar_a_asesor", motivo="lo pidió"),
        AIMessage("Te comunico con un asesor."),
        AIMessage("Claro, ¿qué anillo te interesa?"),  # cotizar sin usar el catálogo: falla
    )
    casos = [
        ("¿Cómo va mi pedido?", "estado_pedido"),
        ("Hola", "saludo"),
        ("Quiero hablar con un asesor", "asesor"),
        ("¿Cuánto cuesta un anillo?", "cotizar"),
    ]
    resultados = evaluar_agente(m, casos)
    assert [r["accion"] for r in resultados] == ["consultar_orden", "conversar", "asesor", "conversar"]
    assert [r["acierto"] for r in resultados] == [True, True, True, False]
    # La orden de prueba existe: el agente la encontró.
    assert "OP-000001" in str(m.recibidos[1])

    mostrar_agente(resultados, "prueba")
    salida = capsys.readouterr().out
    assert "Acción correcta: 75% (3/4)" in salida and "| 4 | ¿Cuánto cuesta un anillo? |" in salida


def test_si_el_modelo_no_responde_se_cuenta_aparte(capsys):
    resultados = evaluar_agente(modelo(falla=True), [("Hola", "saludo")])
    assert resultados[0]["origen"] == "error" and resultados[0]["acierto"] is False
    mostrar_agente(resultados, "prueba")
    assert "Respondió: error 1" in capsys.readouterr().out
