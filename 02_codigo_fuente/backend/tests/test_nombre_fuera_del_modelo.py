import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage, SystemMessage  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agente.seguridad import MARCA_NOMBRE, enmascarar_nombre, poner_nombre  # noqa: E402
from app.agente.servicio import atender_mensaje  # noqa: E402
from app.models import Cliente  # noqa: E402
from tests.test_agente_langchain import catalogo, entorno, llamada, modelo  # noqa: E402,F401


def _enviar(session, cache, texto, m):
    return atender_mensaje(session, cache, "whatsapp", "593999", texto, proveedor=None, modelo=m)


def _todo_lo_que_vio(m):
    return "\n".join(str(x.content) for llamada_ in m.recibidos for x in llamada_)


# --- funciones ---

def test_enmascara_solo_el_nombre_completo():
    assert enmascarar_nombre("Hola Luis, ¿cómo estás?", "Luis") == "Hola {nombre}, ¿cómo estás?"
    assert enmascarar_nombre("hola LUIS", "luis") == "hola {nombre}"
    assert enmascarar_nombre("Algo para Al", "Al") == "Algo para {nombre}"  # no parte "Algo"
    assert enmascarar_nombre("Hola", None) == "Hola"


def test_pone_el_nombre_en_la_marca():
    assert poner_nombre("¡Hola, {nombre}! ¿Qué buscas?", "Luis") == "¡Hola, Luis! ¿Qué buscas?"


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("¡Hola, {nombre}! ¿Qué buscas?", "¡Hola! ¿Qué buscas?"),
        ("{nombre}, ¿qué joya buscas?", "¿qué joya buscas?"),
        ("Claro {nombre}.", "Claro."),
        ("Sin marca", "Sin marca"),
    ],
)
def test_sin_nombre_quita_la_marca_y_arregla_la_frase(texto, esperado):
    assert poner_nombre(texto, None) == esperado


# --- en el agente ---

def _cliente_con_nombre(session, cache, catalogo):
    m = modelo(
        llamada("guardar_preferencias", nombre="Luis"),
        AIMessage("Encantado. ¿Qué joya buscas?"),
    )
    _enviar(session, cache, "soy Luis", m)
    assert session.scalar(select(Cliente)).nombre_preferido == "Luis"


def test_el_prompt_no_lleva_el_nombre_real(session, cache, catalogo):
    _cliente_con_nombre(session, cache, catalogo)
    m = modelo(AIMessage("¡Hola de nuevo, {nombre}! ¿Seguimos?"))
    r = _enviar(session, cache, "hola", m)
    sistema = next(x for x in m.recibidos[0] if isinstance(x, SystemMessage)).content
    assert "Luis" not in sistema
    assert MARCA_NOMBRE in sistema
    assert r.texto == "¡Hola de nuevo, Luis! ¿Seguimos?"  # el servidor puso el nombre


def test_el_historial_no_le_devuelve_al_modelo_el_nombre_que_ya_se_puso(session, cache, catalogo):
    _cliente_con_nombre(session, cache, catalogo)
    _enviar(session, cache, "hola", modelo(AIMessage("¡Qué gusto, {nombre}!")))
    m = modelo(AIMessage("Cuéntame, ¿qué presupuesto tienes?"))
    _enviar(session, cache, "busco argollas", m)
    historial_ia = [x.content for x in m.recibidos[0] if isinstance(x, AIMessage)]
    assert "¡Qué gusto, {nombre}!" in historial_ia
    assert not any("Luis" in c for c in historial_ia)


def test_si_el_modelo_escribe_la_marca_sin_conocer_el_nombre_no_se_ve_en_el_chat(
    session, cache, catalogo
):
    r = _enviar(session, cache, "hola", modelo(AIMessage("¡Hola, {nombre}! ¿Qué joya buscas?")))
    assert "{nombre}" not in r.texto
    assert r.texto == "¡Hola! ¿Qué joya buscas?"
