import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agente import contexto as ctx
from app.agente.llm import ErrorLLM, ProveedorLLM
from app.agente.rutas import get_proveedor
from app.agente.servicio import atender_mensaje, enlace_catalogo
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.models import Cliente, Conversacion, Mensaje, TransicionConversacion


def _enviar(session, cache, texto, id_canal="593999", **kw):
    return atender_mensaje(session, cache, "whatsapp", id_canal, texto, **kw)


# --- extracción de contexto (JOY-29) ---

def test_extrae_categoria_material_quilataje_y_talla():
    datos = ctx.extraer("Busco un anillo de oro 18k talla 7")
    assert datos.contexto == {"categoria": "Anillos", "material": "oro", "quilataje": "18k"}
    assert datos.talla == "7"


def test_extrae_el_nombre():
    assert ctx.extraer("Hola, me llamo maría").nombre == "María"


def test_sin_datos_no_extrae_nada():
    datos = ctx.extraer("hola buenas")
    assert datos.contexto == {} and datos.nombre is None and datos.talla is None


# --- enlaces (JOY-16) ---

def test_enlace_catalogo_lleva_los_filtros(monkeypatch):
    monkeypatch.setenv("WEB_URL", "https://joyeria.test/")
    assert enlace_catalogo({}) == "https://joyeria.test"
    assert (
        enlace_catalogo({"categoria": "Anillos", "material": "oro"})
        == "https://joyeria.test/?categoria=Anillos&material=oro"
    )


# --- servicio de conversación ---

def test_primer_mensaje_crea_cliente_conversacion_y_guarda_ambos_mensajes(session, cache):
    r = _enviar(session, cache, "hola", nombre="Ana Pérez")
    assert r.intencion == "saludo" and r.texto
    assert session.scalars(select(Cliente)).all()[0].nombre_perfil == "Ana Pérez"
    conversacion = session.scalars(select(Conversacion)).one()
    assert conversacion.estado == "activa"
    direcciones = [m.direccion for m in session.scalars(select(Mensaje).order_by(Mensaje.id))]
    assert direcciones == ["entrante", "saliente"]
    transicion = session.scalars(select(TransicionConversacion)).one()
    assert (transicion.estado_anterior, transicion.estado_nuevo) == (None, "activa")


def test_segundo_mensaje_reutiliza_la_conversacion(session, cache):
    _enviar(session, cache, "hola")
    _enviar(session, cache, "quiero ver el catálogo")
    assert len(session.scalars(select(Conversacion)).all()) == 1
    assert len(session.scalars(select(Mensaje)).all()) == 4


def test_recuerda_lo_que_dice_el_cliente_y_lo_usa_despues(session, cache, monkeypatch):
    monkeypatch.setenv("WEB_URL", "https://joyeria.test")
    _enviar(session, cache, "me llamo Luis, busco un anillo de plata talla 9")
    cliente = session.scalars(select(Cliente)).one()
    assert cliente.nombre_preferido == "Luis"
    assert cliente.talla == "9"
    assert cliente.contexto_cualificacion == {"categoria": "Anillos", "material": "plata"}
    r = _enviar(session, cache, "cuánto cuesta?")
    assert "categoria=Anillos" in r.texto and "material=plata" in r.texto
    assert "Luis" in r.texto
    saludo = _enviar(session, cache, "hola de nuevo")
    assert "anillos de plata" in saludo.texto


def test_si_menciona_una_joya_sin_pedir_nada_se_le_muestra_el_catalogo(session, cache, monkeypatch):
    monkeypatch.setenv("WEB_URL", "https://joyeria.test")
    r = _enviar(session, cache, "busco un anillo de plata")
    assert r.intencion == "catalogo"
    assert "categoria=Anillos" in r.texto and "material=plata" in r.texto


def test_el_contexto_se_acumula_sin_perder_lo_anterior(session, cache):
    _enviar(session, cache, "quiero una cadena")
    _enviar(session, cache, "de oro 18k")
    cliente = session.scalars(select(Cliente)).one()
    assert cliente.contexto_cualificacion == {
        "categoria": "Cadenas", "material": "oro", "quilataje": "18k"
    }


def test_pedir_asesor_escala_y_luego_el_agente_calla(session, cache):
    r = _enviar(session, cache, "quiero hablar con un asesor")
    assert r.escalada and r.intencion == "asesor"
    assert session.scalars(select(Conversacion)).one().estado == "escalada"
    estados = [
        (t.estado_anterior, t.estado_nuevo)
        for t in session.scalars(select(TransicionConversacion).order_by(TransicionConversacion.id))
    ]
    assert estados == [(None, "activa"), ("activa", "escalada")]

    callado = _enviar(session, cache, "hola?")
    assert callado.texto is None and callado.escalada
    mensajes = session.scalars(select(Mensaje).order_by(Mensaje.id)).all()
    assert [m.direccion for m in mensajes] == ["entrante", "saliente", "entrante"]


def test_estado_de_pedido_pasa_a_un_asesor(session, cache):
    r = _enviar(session, cache, "dónde está mi pedido")
    assert r.escalada and "asesor" in r.texto


def test_mensaje_repetido_no_se_procesa_dos_veces(session, cache):
    primero = _enviar(session, cache, "hola", id_externo="wamid.1")
    repetido = _enviar(session, cache, "hola", id_externo="wamid.1")
    assert not primero.duplicado
    assert repetido.duplicado and repetido.texto is None
    assert len(session.scalars(select(Mensaje)).all()) == 2


def test_clientes_distintos_tienen_conversaciones_distintas(session, cache):
    _enviar(session, cache, "hola", id_canal="1")
    _enviar(session, cache, "hola", id_canal="2")
    assert len(session.scalars(select(Conversacion)).all()) == 2


def test_una_conversacion_cerrada_se_reemplaza_por_una_nueva(session, cache):
    _enviar(session, cache, "hola")
    session.scalars(select(Conversacion)).one().estado = "cerrada"
    session.commit()
    _enviar(session, cache, "hola otra vez")
    assert len(session.scalars(select(Conversacion)).all()) == 2


class LlmQueRegresa(ProveedorLLM):
    def __init__(self, etiqueta):
        self.etiqueta = etiqueta

    def generar(self, sistema, usuario):
        return self.etiqueta


class LlmCaido(ProveedorLLM):
    def generar(self, sistema, usuario):
        raise ErrorLLM("sin servicio")


def test_usa_la_intencion_del_modelo(session, cache):
    r = _enviar(session, cache, "mmm no sé", proveedor=LlmQueRegresa("catalogo"))
    assert r.intencion == "catalogo"


def test_si_el_modelo_falla_responde_con_reglas(session, cache):
    r = _enviar(session, cache, "hola", proveedor=LlmCaido())
    assert r.intencion == "saludo" and r.texto


# --- endpoint ---

@pytest.fixture
def cliente_http(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_responde_al_mensaje(cliente_http):
    r = cliente_http.post(
        "/agente/mensajes",
        json={"canal": "whatsapp", "id_canal": "593111", "texto": "hola", "nombre": "Ana"},
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["intencion"] == "saludo" and cuerpo["respuesta"]
    assert cuerpo["escalada"] is False and cuerpo["duplicado"] is False


def test_endpoint_rechaza_canal_invalido_y_texto_vacio(cliente_http):
    malo = {"canal": "telegram", "id_canal": "1", "texto": "hola"}
    assert cliente_http.post("/agente/mensajes", json=malo).status_code == 422
    vacio = {"canal": "whatsapp", "id_canal": "1", "texto": ""}
    assert cliente_http.post("/agente/mensajes", json=vacio).status_code == 422
