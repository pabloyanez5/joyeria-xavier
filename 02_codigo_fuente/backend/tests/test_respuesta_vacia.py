import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agente.lc_agente import AVISO_RESPUESTA_VACIA  # noqa: E402
from app.agente.servicio import atender_mensaje  # noqa: E402
from app.models import Cliente  # noqa: E402
from tests.test_agente_langchain import llamada, modelo  # noqa: E402


def _enviar(session, cache, texto, m):
    return atender_mensaje(session, cache, "whatsapp", "593999", texto, proveedor=None, modelo=m)


def test_si_el_modelo_calla_tras_guardar_un_dato_se_le_pide_la_respuesta(session, cache):
    m = modelo(
        llamada("guardar_preferencias", ocasion="aniversario"),
        AIMessage(""),  # Gemini guarda el dato y se queda sin decir nada
        AIMessage("¡Qué lindo! ¿Qué presupuesto tienes pensado?"),
    )
    r = _enviar(session, cache, "es para mi aniversario", m)
    assert r.texto == "¡Qué lindo! ¿Qué presupuesto tienes pensado?"
    assert r.intencion == "guardar_preferencias"
    assert session.scalar(select(Cliente)).contexto_cualificacion["ocasion"] == "aniversario"
    ultimo = m.recibidos[2][-1]  # lo que vio el modelo en la tercera llamada
    assert isinstance(ultimo, HumanMessage) and ultimo.content == AVISO_RESPUESTA_VACIA
    # el mensaje vacío del modelo no se le reenvía
    assert not any(isinstance(x, AIMessage) and x.content == "" and not x.tool_calls for x in m.recibidos[2])


def test_si_sigue_callado_se_usa_el_motor_de_reglas(session, cache):
    m = modelo(AIMessage(""), AIMessage(""))
    r = _enviar(session, cache, "hola", m)
    assert r.texto  # respondió el motor de reglas, no quedó en silencio
    assert r.intencion == "saludo"
