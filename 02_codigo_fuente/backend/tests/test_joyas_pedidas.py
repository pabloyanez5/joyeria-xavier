"""JOY-79: una joya de la ficha que ya tiene orden no se ofrece para crearla otra vez."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agente import intereses
from app.agente.servicio import atender_mensaje
from app.db import get_session
from app.main import app
from app.models import Cliente, Orden
from app.webhook import get_enviador
from tests.conftest import datos_de_orden

TEL = "593987000222"
FICHA = {
    "intereses": [
        {"categoria": "Aretes", "material": "oro", "presupuesto": "400 dólares"},
        {"categoria": "Cadenas", "material": "plata", "presupuesto": "800 dólares"},
    ],
    "activo": 1,
}


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_enviador, None)


@pytest.fixture
def conversacion(session, cache):
    r = atender_mensaje(session, cache, "whatsapp", TEL, "hola", nombre="Pablo Yánez")
    cliente = session.scalar(select(Cliente).where(Cliente.id_canal == TEL))
    cliente.contexto_cualificacion = dict(FICHA)
    session.commit()
    return r.conversacion_id, cliente


def _detalle(api, conversacion_id):
    return api.get(f"/conversaciones/{conversacion_id}").json()


def _joya(descripcion, interes=None):
    joya = datos_de_orden(descripcion=descripcion)
    joya.pop("nombre_completo")
    joya.pop("telefono")
    if interes:
        joya["interes"] = interes
    return joya


def test_sin_ordenes_las_dos_joyas_se_pueden_pedir(api, conversacion):
    detalle = _detalle(api, conversacion[0])
    assert [i["orden"] for i in detalle["intereses"]] == [None, None]


def test_la_orden_de_una_joya_queda_en_su_ficha(api, conversacion):
    conversacion_id, cliente = conversacion
    r = api.post("/ordenes", json=datos_de_orden(
        cliente_id=cliente.id, descripcion="Aretes de oro", interes=1))
    assert r.status_code == 201, r.text

    aretes, cadena = _detalle(api, conversacion_id)["intereses"]
    assert aretes["orden"] == r.json()["codigo"]
    assert aretes["etapa_de_la_orden"] == "por_verificar"
    assert cadena["orden"] is None


def test_el_pedido_marca_cada_joya_con_su_orden(api, conversacion):
    conversacion_id, cliente = conversacion
    cuerpo = {
        "cliente_id": cliente.id,
        "nombre_completo": "Pablo Yánez",
        "telefono": "0991234567",
        "joyas": [_joya("Aretes de oro", 1), _joya("Cadena de plata", 2)],
    }
    r = api.post("/ordenes/pedido", json=cuerpo)
    assert r.status_code == 201, r.text
    codigos = [o["codigo"] for o in r.json()["ordenes"]]

    assert [i["orden"] for i in _detalle(api, conversacion_id)["intereses"]] == codigos


def test_una_joya_agregada_a_mano_no_marca_nada(api, conversacion):
    conversacion_id, cliente = conversacion
    api.post("/ordenes", json=datos_de_orden(cliente_id=cliente.id, descripcion="Dije de oro"))
    assert [i["orden"] for i in _detalle(api, conversacion_id)["intereses"]] == [None, None]


def test_un_numero_de_joya_que_no_existe_se_ignora(api, conversacion):
    _, cliente = conversacion
    r = api.post("/ordenes", json=datos_de_orden(
        cliente_id=cliente.id, descripcion="Anillo", interes=5))
    assert r.status_code == 201
    assert all("orden_id" not in i for i in intereses.lista(cliente.contexto_cualificacion))


def test_las_ordenes_creadas_antes_se_reconocen_por_la_descripcion(api, session, conversacion):
    conversacion_id, cliente = conversacion
    origen = f"Origen: conversación #{conversacion_id} por whatsapp."
    orden = Orden(cliente_id=cliente.id, etapa_actual="en_produccion",
                  descripcion=f"Joya: Cadenas; Material: plata. {origen}")
    session.add(orden)
    session.commit()

    aretes, cadena = _detalle(api, conversacion_id)["intereses"]
    assert aretes["orden"] is None
    assert cadena["orden"] == f"OP-{orden.id:06d}"
    assert cadena["etapa_de_la_orden"] == "en_produccion"


def test_otra_joya_de_una_categoria_ya_pedida_abre_un_interes_nuevo():
    contexto = intereses.marcar_pedidas(FICHA, {1: 28})
    contexto = intereses.anotar(contexto, categoria="Aretes", material="plata")

    aretes, cadena, nuevos = intereses.lista(contexto)
    assert aretes == {**FICHA["intereses"][0], "orden_id": 28}  # la pedida no cambia
    assert nuevos == {"categoria": "Aretes", "material": "plata"}
    assert contexto["activo"] == 2


def test_el_modelo_sabe_que_joyas_ya_tienen_orden():
    contexto = intereses.marcar_pedidas(FICHA, {2: 29})
    assert "ya tiene su orden OP-000029" in intereses.resumen(contexto)
