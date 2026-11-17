"""El respaldo también cubre al modelo que se queda callado, y la bitácora queda en archivo."""
import logging

import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage  # noqa: E402

from app import bitacora  # noqa: E402
from app.agente import lc_agente  # noqa: E402
from app.agente.servicio import atender_mensaje  # noqa: E402
from app.models import Mensaje  # noqa: E402
from tests.test_agente_langchain import llamada, modelo  # noqa: E402


def _enviar(session, cache, texto, principal):
    return atender_mensaje(
        session, cache, "whatsapp", "593999", texto, proveedor=None, modelo=principal
    )


def test_si_el_principal_calla_dos_veces_contesta_el_respaldo(session, cache, monkeypatch):
    # Así cayó a reglas el "¿Cómo va mi pedido?" del 17-nov: consultó la orden y no escribió nada.
    principal = modelo(llamada("consultar_orden"), AIMessage(""), AIMessage(""))
    respaldo = modelo(AIMessage("Tus aretes están en producción."))
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: respaldo)

    r = _enviar(session, cache, "¿Cómo va mi pedido?", principal)

    assert r.texto == "Tus aretes están en producción."
    guardado = session.query(Mensaje).filter_by(direccion="saliente").one()
    assert guardado.origen == "respaldo"


def test_si_callan_los_dos_responde_el_motor_de_reglas(session, cache, monkeypatch):
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: modelo(AIMessage("")))
    principal = modelo(AIMessage(""), AIMessage(""))

    r = _enviar(session, cache, "hola", principal)

    assert r.texto and r.intencion == "saludo"


def test_el_log_dice_por_que_fallo_sin_mostrar_la_clave(session, cache, monkeypatch, caplog):
    class Caido:
        def bind_tools(self, *_a, **_k):
            return self

        def invoke(self, *_a, **_k):
            raise RuntimeError("429 RESOURCE_EXHAUSTED key=AIzaSyA1234567890abcdefghijklmnop")

    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: None)
    with caplog.at_level(logging.WARNING, logger="joyeria"):
        _enviar(session, cache, "hola", Caido())

    assert "RuntimeError: 429 RESOURCE_EXHAUSTED" in caplog.text
    # Lo que va a la consola y al archivo, traza del error incluida, sale sin la clave.
    escrito = "\n".join(bitacora.Formato().format(r) for r in caplog.records)
    assert "429 RESOURCE_EXHAUSTED" in escrito and "Traceback" in escrito
    assert "AIzaSyA1234567890" not in escrito


def test_la_bitacora_escribe_en_el_archivo(tmp_path, monkeypatch):
    registro = logging.getLogger("joyeria")
    antes = list(registro.handlers)
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setattr(registro, "_configurada", False, raising=False)
    try:
        bitacora.configurar()
        logging.getLogger("joyeria.prueba").warning("respondió el motor de reglas")
        for h in registro.handlers:
            h.flush()
        assert "respondió el motor de reglas" in (tmp_path / "api.log").read_text(encoding="utf-8")
    finally:
        for h in registro.handlers:
            if h not in antes:
                registro.removeHandler(h)
                h.close()


def test_sin_claves_tapa_las_claves_de_google():
    assert bitacora.sin_claves("x AIzaSyA1234567890abcdefghijklmnop y") == "x AIza*** y"
