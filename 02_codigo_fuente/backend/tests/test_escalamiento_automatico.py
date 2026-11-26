"""JOY-85 · Escalamiento automático cuando el agente no puede resolver (RF-01, RNF-02).

Criterios: casos de prueba de cada motivo terminan en «espera a un asesor» con su motivo; el
agente no escala una consulta que sí puede resolver.
"""
import pytest

pytest.importorskip("langchain_core")

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app.agente import escalamiento  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Conversacion, Mensaje, Usuario  # noqa: E402
from app.webhook import get_enviador  # noqa: E402
from tests.test_agente_langchain import _enviar, catalogo, entorno, llamada, modelo  # noqa: E402,F401


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def _motivo(api, conversacion_id):
    return api.get(f"/conversaciones/{conversacion_id}").json()["motivo_escalamiento"]


AUTOMATICOS = [
    ("molesto", "Esto es una estafa, nadie me responde", "El cliente está molesto"),
    ("molesto", "Pésimo servicio, ya les dije tres veces", "El cliente está molesto"),
    ("sin_herramienta", "¿Hacen reparaciones? Se me rompió la cadena", "reparación"),
    ("sin_herramienta", "quiero agrandar la talla de mi anillo", "ajuste de talla"),
    ("sin_herramienta", "¿pueden grabar mis iniciales en la argolla?", "grabado"),
    ("sin_herramienta", "tengo mi propio diseño, ¿lo pueden hacer?", "diseño a medida"),
    ("sin_herramienta", "quiero devolver los aretes", "devolución o garantía"),
    ("sin_herramienta", "necesito factura con mi RUC", "factura"),
    ("fuera_de_rango", "quiero un anillo de oro 24k", "otro quilataje (24k)"),
    ("fuera_de_rango", "¿tienen argollas de platino?", "otro material (platino)"),
    ("fuera_de_rango", "tengo 8000 dólares para un collar", "presupuesto de $8000"),
]


@pytest.mark.parametrize("tipo, texto, motivo", AUTOMATICOS, ids=[t for _, t, _ in AUTOMATICOS])
def test_cada_motivo_pasa_a_un_asesor_sin_llamar_al_modelo(api, session, cache, catalogo, tipo, texto, motivo):
    m = modelo()  # si el mensaje le llegara al modelo, fallaría
    r = _enviar(session, cache, texto, m)
    assert r.escalada and r.texto == escalamiento.RESPUESTAS[tipo]
    assert m.recibidos == []
    assert session.get(Conversacion, r.conversacion_id).estado == "escalada"
    assert motivo in _motivo(api, r.conversacion_id)


def test_queda_asignada_a_un_asesor(session, cache, catalogo):
    session.add(Usuario(nombre="Ana", email="ana@x.com", rol="asesor"))
    session.commit()
    r = _enviar(session, cache, "estoy muy molesto con mi pedido", modelo())
    assert session.get(Conversacion, r.conversacion_id).asesor_id is not None


def test_la_respuesta_queda_con_origen_escalamiento(session, cache, catalogo):
    r = _enviar(session, cache, "quiero agendar una cita", modelo())
    ultimo = session.query(Mensaje).filter_by(conversacion_id=r.conversacion_id, direccion="saliente").one()
    assert ultimo.origen == "escalamiento"


# --- dos mensajes seguidos sin entender (motor de reglas) ---

def test_al_segundo_mensaje_que_no_entiende_pasa_a_un_asesor(api, session, cache):
    primero = _enviar(session, cache, "asdfgh")
    assert not primero.escalada and "No estoy seguro" in primero.texto
    segundo = _enviar(session, cache, "qwerty zxcv")
    assert segundo.escalada and segundo.texto == escalamiento.RESPUESTAS["no_entendido"]
    assert _motivo(api, segundo.conversacion_id) == "El agente no entendió dos mensajes seguidos"


def test_si_entre_medio_entiende_la_cuenta_vuelve_a_cero(session, cache, catalogo):
    _enviar(session, cache, "asdfgh")
    _enviar(session, cache, "quiero ver anillos")
    r = _enviar(session, cache, "qwerty zxcv")
    assert not r.escalada


def test_el_modelo_tiene_la_misma_indicacion():
    from app.agente.lc_agente import INSTRUCCIONES

    assert "tampoco lo entiendes, derívalo a un asesor" in INSTRUCCIONES


# --- el motivo también queda cuando escala por otras vías ---

def test_si_lo_pide_el_motivo_queda_en_la_ficha(api, session, cache):
    r = _enviar(session, cache, "quiero hablar con un asesor")  # motor de reglas
    assert _motivo(api, r.conversacion_id) == "El cliente pidió hablar con un asesor"


def test_si_deriva_el_modelo_queda_su_motivo(api, session, cache, catalogo):
    m = modelo(llamada("derivar_a_asesor", motivo="Quiere un juego de joyas para 20 invitados"), AIMessage("Te comunico con un asesor."))
    r = _enviar(session, cache, "necesito 20 dijes para regalar en mi boda", m)
    assert r.escalada and _motivo(api, r.conversacion_id) == "Quiere un juego de joyas para 20 invitados"


# --- lo que sí puede resolver no se escala ---

@pytest.mark.parametrize(
    "texto",
    [
        "¿cuánto cuesta un anillo de oro 18k?",
        "quiero ver aretes de plata",
        "tengo 400 dólares para un regalo",
        "¿Aceptan tarjeta de crédito?",
        "¿le molesta si pago mañana?",
        "disculpe la molestia, ¿tienen cadenas?",
        "¡Gracias!!!",
        "HOLA QUIERO UN ANILLO",
    ],
)
def test_no_escala_lo_que_si_puede_resolver(session, cache, catalogo, texto):
    m = modelo(AIMessage("¡Con gusto! ¿Qué joya buscas?"))
    r = _enviar(session, cache, texto, m)
    assert not r.escalada and len(m.recibidos) == 1


@pytest.mark.parametrize("valor, esperado", [("", 5000), ("12000", 12000), ("abc", 5000), ("0", 5000)])
def test_el_maximo_cotizable_es_configurable(monkeypatch, valor, esperado):
    monkeypatch.setenv("AGENTE_COTIZACION_MAXIMA", valor)
    assert escalamiento.maximo_cotizable() == esperado
