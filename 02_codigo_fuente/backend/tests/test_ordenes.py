import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.models import Cliente, HistorialEtapa, Orden, Producto, Usuario


@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def datos(session):
    cliente = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana Pérez")
    producto = Producto(nombre="Anillo sello", categoria="Anillos", activo=True)
    asesor = Usuario(nombre="Luis", email="luis@x.com", rol="asesor")
    taller = Usuario(nombre="Marta", email="marta@x.com", rol="taller")
    session.add_all([cliente, producto, asesor, taller])
    session.commit()
    return {"cliente": cliente, "producto": producto, "asesor": asesor, "taller": taller}


def _crear(api, datos, **extra):
    cuerpo = {
        "cliente_id": datos["cliente"].id,
        "producto_id": datos["producto"].id,
        "descripcion": "Anillo sello en oro 18k, grabado con iniciales A.P.",
        **extra,
    }
    return api.post("/ordenes", json=cuerpo)


def test_crea_la_orden_y_queda_publicada_en_la_cola_con_acuse_pendiente(api, datos):
    inicio = time.perf_counter()
    r = _crear(api, datos, usuario_id=datos["asesor"].id)
    cola = api.get("/ordenes/cola").json()
    assert time.perf_counter() - inicio <= 3  # criterio de aceptación: ≤ 3 s
    assert r.status_code == 201
    orden = r.json()
    assert orden["codigo"] == f"OP-{orden['id']:06d}"
    assert orden["etapa_actual"] == "en_cola"
    assert orden["acuse_pendiente"] is True
    assert orden["publicada_en"] is not None
    assert orden["cliente"] == "Ana Pérez" and orden["producto"] == "Anillo sello"
    assert [o["id"] for o in cola] == [orden["id"]]
    assert cola[0]["acuse_pendiente"] is True


def test_cada_orden_tiene_un_id_unico(api, datos):
    ids = {_crear(api, datos).json()["id"] for _ in range(3)}
    assert len(ids) == 3


def test_guarda_el_historial_con_el_asesor(api, session, datos):
    orden = _crear(api, datos, usuario_id=datos["asesor"].id).json()
    h = session.scalars(select(HistorialEtapa).where(HistorialEtapa.orden_id == orden["id"])).one()
    assert (h.etapa, h.usuario_id) == ("en_cola", datos["asesor"].id)


def test_se_puede_crear_sin_producto_para_una_joya_a_medida(api, datos):
    r = api.post(
        "/ordenes",
        json={"cliente_id": datos["cliente"].id, "descripcion": "Dije a medida en plata"},
    )
    assert r.status_code == 201 and r.json()["producto"] is None


def test_rechaza_cliente_producto_o_usuario_inexistentes(api, datos):
    assert api.post("/ordenes", json={"cliente_id": 999, "descripcion": "algo"}).status_code == 404
    assert _crear(api, datos, producto_id=999).status_code == 404
    assert _crear(api, datos, usuario_id=999).status_code == 404


def test_solo_un_asesor_puede_crear_ordenes(api, datos):
    r = _crear(api, datos, usuario_id=datos["taller"].id)
    assert r.status_code == 422


def test_rechaza_una_descripcion_vacia(api, datos):
    assert _crear(api, datos, descripcion="  ").status_code == 422


def test_la_cola_va_de_la_mas_antigua_a_la_mas_nueva_y_solo_trae_las_pendientes_del_taller(
    api, session, datos
):
    primera = _crear(api, datos).json()
    segunda = _crear(api, datos).json()
    session.add(
        Orden(
            cliente_id=datos["cliente"].id,
            descripcion="ya en producción",
            etapa_actual="en_produccion",
        )
    )
    session.commit()
    assert [o["id"] for o in api.get("/ordenes/cola").json()] == [primera["id"], segunda["id"]]


def test_el_taller_confirma_el_acuse(api, datos):
    orden = _crear(api, datos).json()
    r = api.post(f"/ordenes/{orden['id']}/acuse")
    assert r.status_code == 200 and r.json()["acuse_pendiente"] is False
    assert api.post(f"/ordenes/{orden['id']}/acuse").json()["acuse_pendiente"] is False
    assert api.get(f"/ordenes/{orden['id']}").json()["acuse_pendiente"] is False
    assert api.post("/ordenes/999/acuse").status_code == 404


def test_detalle_de_orden_inexistente(api):
    assert api.get("/ordenes/999").status_code == 404


def test_lista_de_clientes_para_el_panel(api, session, datos):
    session.add(Cliente(canal="instagram", id_canal="ig1"))
    session.commit()
    r = api.get("/clientes")
    assert r.status_code == 200
    nombres = {c["nombre"] for c in r.json()}
    assert "Ana Pérez" in nombres and len(nombres) == 2
