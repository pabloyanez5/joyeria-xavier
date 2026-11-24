"""JOY-94 · Resiliencia del agente ante caídas del modelo.

Antecedente: el 23-nov-2026 Google respondió 503 en los dos modelos durante más de una hora y el
agente contestó con el motor de reglas, a veces con «No estoy seguro de haber entendido».
"""
import pytest

pytest.importorskip("langchain_core")

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app.agente import intereses, lc_agente  # noqa: E402
from app.agente.contexto import ocasion_y_presupuesto  # noqa: E402
from app.agente.lc_agente import es_pasajero  # noqa: E402
from app.cache import get_cache  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Mensaje  # noqa: E402
from tests.test_agente_langchain import ModeloGuion, _cliente, _enviar, catalogo, entorno, modelo  # noqa: E402,F401

SATURADO = "503 UNAVAILABLE. This model is currently experiencing high demand."


class ModeloSaturado(ModeloGuion):
    """Falla con un 503 las primeras `fallas` veces y luego responde lo guionado."""

    fallas: int = 0
    llamadas: int = 0
    error: str = SATURADO

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.llamadas += 1
        if self.fallas > 0:
            self.fallas -= 1
            raise RuntimeError(self.error)
        return super()._generate(messages, stop, run_manager, **kwargs)


def saturado(*respuestas, fallas=1, error=SATURADO):
    return ModeloSaturado(respuestas=list(respuestas), recibidos=[], fallas=fallas, error=error)


def _origen(session):
    return session.query(Mensaje).filter_by(direccion="saliente").order_by(Mensaje.id.desc()).first().origen


@pytest.fixture
def con_respaldo(monkeypatch):
    respaldo = modelo(AIMessage("Respuesta del respaldo."))
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: respaldo)
    return respaldo


# --- 1. reintento ante un 503 momentáneo ---

def test_un_503_momentaneo_se_supera_con_el_reintento(session, cache, catalogo, con_respaldo, caplog):
    principal = saturado(AIMessage("¡Hola! ¿Qué joya buscas?"), fallas=1)
    r = _enviar(session, cache, "hola", principal)
    assert r.texto == "¡Hola! ¿Qué joya buscas?"
    assert principal.llamadas == 2 and con_respaldo.recibidos == []  # ni respaldo ni reglas
    assert _origen(session) == "modelo"
    assert any("se reintenta" in m for m in caplog.messages)


def test_si_sigue_saturado_contesta_el_respaldo(session, cache, catalogo, con_respaldo):
    principal = saturado(fallas=5)
    r = _enviar(session, cache, "hola", principal)
    assert r.texto == "Respuesta del respaldo."
    assert principal.llamadas == 2  # un solo reintento: no se demora la respuesta
    assert _origen(session) == "respaldo"


def test_un_error_que_no_es_pasajero_no_se_reintenta(session, cache, catalogo, con_respaldo):
    principal = saturado(fallas=1, error="400 INVALID_ARGUMENT: clave mal escrita")
    r = _enviar(session, cache, "hola", principal)
    assert principal.llamadas == 1 and r.texto == "Respuesta del respaldo."


def test_el_reintento_se_puede_apagar(session, cache, catalogo, con_respaldo, monkeypatch):
    monkeypatch.setenv("AGENTE_REINTENTO_SEGUNDOS", "0")
    principal = saturado(AIMessage("no debía llegar"), fallas=1)
    _enviar(session, cache, "hola", principal)
    assert principal.llamadas == 1 and _origen(session) == "respaldo"


def test_si_todo_falla_igual_responde_el_motor_de_reglas(session, cache, catalogo, monkeypatch):
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: saturado(fallas=9))
    r = _enviar(session, cache, "hola", saturado(fallas=9))
    assert r.texto and _origen(session) == "reglas"


@pytest.mark.parametrize(
    "mensaje, pasajero",
    [
        (SATURADO, True),
        ("504 DEADLINE_EXCEEDED", True),
        ("Read timed out", True),
        ("400 INVALID_ARGUMENT", False),
        ("403 PERMISSION_DENIED: API key not valid", False),
    ],
)
def test_que_errores_cuentan_como_pasajeros(mensaje, pasajero):
    assert es_pasajero(RuntimeError(mensaje)) is pasajero


@pytest.mark.parametrize("valor, esperado", [("", 1.5), ("2", 2.0), ("abc", 1.5), ("-1", 0.0), ("60", 5.0)])
def test_la_espera_del_reintento_es_configurable_y_acotada(monkeypatch, valor, esperado):
    monkeypatch.setenv("AGENTE_REINTENTO_SEGUNDOS", valor)
    assert lc_agente.segundos_antes_de_reintentar() == esperado


# --- 2. el motor de reglas no pierde el hilo ---

def test_sin_modelo_la_ocasion_se_anota_y_pregunta_el_material(session, cache, catalogo):
    _enviar(session, cache, "busco un anillo")
    r = _enviar(session, cache, "Es para un aniversario")
    assert "no estoy seguro" not in r.texto.lower()
    assert r.texto.startswith("Anotado") and "es para un aniversario" in r.texto
    assert "¿La prefieres en oro o en plata?" in r.texto
    activo = intereses.activo(_cliente(session).contexto_cualificacion)
    assert activo["categoria"] == "Anillos" and activo["ocasion"] == "aniversario"


def test_sin_modelo_el_presupuesto_se_anota_y_pregunta_el_tipo_de_joya(session, cache, catalogo):
    r = _enviar(session, cache, "tengo 300$")
    assert "tu presupuesto es de $300" in r.texto and "tipo de joya" in r.texto
    assert intereses.activo(_cliente(session).contexto_cualificacion)["presupuesto"] == "$300"


def test_con_joya_y_material_ya_ofrece_las_opciones(session, cache, catalogo):
    _enviar(session, cache, "quiero aretes de oro")
    r = _enviar(session, cache, "es para un cumpleaños, hasta 250 dólares")
    assert "es para un cumpleaños, con un presupuesto de $250" in r.texto
    assert "categoria=Aretes" in r.texto and "material=oro" in r.texto


def test_un_mensaje_sin_datos_sigue_ofreciendo_el_menu(session, cache, catalogo):
    r = _enviar(session, cache, "mmm no sé")
    assert "No estoy seguro" in r.texto


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Es para un aniversario", {"ocasion": "aniversario"}),
        ("Tengo 300$", {"presupuesto": "$300"}),
        ("mi presupuesto es 250", {"presupuesto": "$250"}),
        ("para el día de la madre, unos 80 USD", {"ocasion": "día de la madre", "presupuesto": "$80"}),
        ("anillo de oro 18k talla 7", {}),
        ("¿cómo va mi orden OP-000031?", {}),
        ("tengo 2 hijos", {}),
    ],
)
def test_que_reconoce_como_ocasion_y_presupuesto(texto, esperado):
    assert ocasion_y_presupuesto(texto) == esperado


# --- 3. medir la disponibilidad ---

def test_las_metricas_dicen_que_parte_respondio_la_ia(session, cache, catalogo, monkeypatch):
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: modelo(AIMessage("Del respaldo.")))
    _enviar(session, cache, "hola", modelo(AIMessage("Del modelo.")), id_canal="1")
    _enviar(session, cache, "hola", saturado(fallas=9), id_canal="2")  # respaldo
    monkeypatch.setattr(lc_agente, "respaldo_desde_entorno", lambda: None)
    _enviar(session, cache, "hola", saturado(fallas=9), id_canal="3")  # reglas
    _enviar(session, cache, "hola", None, id_canal="4")  # reglas (sin modelo)

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    try:
        r = TestClient(app).get("/metricas").json()
    finally:
        app.dependency_overrides.clear()
    assert {k: r["respuestas_por_origen"][k] for k in ("modelo", "respaldo", "reglas")} == {
        "modelo": 1, "respaldo": 1, "reglas": 2,
    }
    assert r["respuestas_con_ia"] == 50.0
