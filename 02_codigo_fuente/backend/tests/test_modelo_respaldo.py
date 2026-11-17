import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage  # noqa: E402

from app.agente import lc_agente  # noqa: E402
from app.agente.servicio import atender_mensaje  # noqa: E402
from tests.test_agente_langchain import modelo  # noqa: E402


def _enviar(session, cache, texto, principal):
    return atender_mensaje(
        session, cache, "whatsapp", "593999", texto, proveedor=None, modelo=principal
    )


def test_si_el_modelo_principal_esta_saturado_contesta_el_de_respaldo(session, cache, monkeypatch):
    respaldo = modelo(AIMessage("Con gusto. ¿Qué material prefieres?"))
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: respaldo)
    r = _enviar(session, cache, "busco argollas", modelo(falla=True))
    assert r.texto == "Con gusto. ¿Qué material prefieres?"
    assert r.intencion == "conversacion"


def test_si_el_principal_responde_no_se_usa_el_respaldo(session, cache, monkeypatch):
    respaldo = modelo(AIMessage("no debía usarse"))
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: respaldo)
    r = _enviar(session, cache, "hola", modelo(AIMessage("¡Hola! ¿Qué buscas?")))
    assert r.texto == "¡Hola! ¿Qué buscas?"
    assert respaldo.recibidos == []


def test_si_fallan_los_dos_modelos_responde_el_motor_de_reglas(session, cache, monkeypatch):
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: modelo(falla=True))
    r = _enviar(session, cache, "hola", modelo(falla=True))
    assert r.texto and r.intencion == "saludo"


def test_el_respaldo_se_configura_por_entorno(monkeypatch):
    monkeypatch.setattr(lc_agente, "_modelo_de_respaldo", lambda clave, nombre: (clave, nombre))
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert lc_agente.respaldo_desde_entorno() == ("k", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_MODEL_RESPALDO", "gemini-flash-latest")
    assert lc_agente.respaldo_desde_entorno() == ("k", "gemini-flash-latest")
    monkeypatch.setenv("GEMINI_MODEL_RESPALDO", "ninguno")
    assert lc_agente.respaldo_desde_entorno() is None
    monkeypatch.setenv("GEMINI_MODEL_RESPALDO", "gemini-3.1-flash-lite")
    assert lc_agente.respaldo_desde_entorno() is None  # igual al principal: no sirve de respaldo
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GEMINI_MODEL_RESPALDO", "gemini-flash-latest")
    assert lc_agente.respaldo_desde_entorno() is None  # sin clave no hay modelo
