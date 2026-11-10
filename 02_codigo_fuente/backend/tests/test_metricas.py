from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.agente.servicio import atender_mensaje
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.models import Cliente, Conversacion, HistorialEtapa, Orden, Usuario
from app.webhook import get_enviador


@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_sin_datos_no_inventa_porcentajes(api):
    r = api.get("/metricas").json()
    assert r["conversaciones"] == 0 and r["tasa_resolucion_agente"] is None
    assert r["horas_promedio_entrega"] is None
    assert [e["ordenes"] for e in r["ordenes_por_etapa"]] == [0, 0, 0, 0]
    assert len(r["conversaciones_por_dia"]) == 7


def test_resolucion_autonoma_frente_a_escalamientos(api, session, cache):
    atender_mensaje(session, cache, "whatsapp", "593111", "hola")
    atender_mensaje(session, cache, "whatsapp", "593222", "hola")
    atender_mensaje(session, cache, "whatsapp", "593222", "quiero hablar con un asesor")
    atender_mensaje(session, cache, "whatsapp", "593333", "hola")
    atender_mensaje(session, cache, "whatsapp", "593333", "gracias")
    r = api.get("/metricas").json()
    assert r["conversaciones"] == 3
    assert r["escaladas"] == 1 and r["resueltas_por_agente"] == 2
    assert r["tasa_resolucion_agente"] == 66.7
    assert r["por_estado"]["escalada"] == 1 and r["por_estado"]["activa"] == 2
    assert r["clientes"] == 3
    assert r["mensajes"]["cliente"] >= 5 and r["mensajes"]["agente"] >= 3


def test_una_conversacion_reactivada_sigue_contando_como_escalada(api, session, cache):
    atender_mensaje(session, cache, "whatsapp", "593222", "hola")
    atender_mensaje(session, cache, "whatsapp", "593222", "quiero hablar con un asesor")
    conv = session.query(Conversacion).one()
    assert api.post(f"/conversaciones/{conv.id}/reactivar").status_code == 200
    r = api.get("/metricas").json()
    assert r["escaladas"] == 1 and r["por_estado"]["activa"] == 1


def test_solo_cuenta_el_periodo_pedido(api, session, cache):
    atender_mensaje(session, cache, "whatsapp", "593111", "hola")
    vieja = session.query(Conversacion).one()
    vieja.creado_en = datetime.now(timezone.utc) - timedelta(days=40)
    session.commit()
    assert api.get("/metricas?dias=30").json()["conversaciones"] == 0
    assert api.get("/metricas?dias=90").json()["conversaciones"] == 1
    assert api.get("/metricas?dias=0").status_code == 422


def test_ordenes_por_etapa_y_tiempo_de_entrega(api, session):
    cliente = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana")
    taller = Usuario(nombre="Marta", email="m@x.com", rol="taller")
    session.add_all([cliente, taller])
    session.commit()
    ids = [
        api.post("/ordenes", json={"cliente_id": cliente.id, "descripcion": f"Joya {i}"}).json()["id"]
        for i in range(3)
    ]
    for etapa in ("en_produccion", "terminada", "entregada"):
        api.post(f"/ordenes/{ids[0]}/etapa", json={"etapa": etapa, "avisar_al_cliente": False})
    api.post(f"/ordenes/{ids[1]}/etapa", json={"etapa": "en_produccion", "avisar_al_cliente": False})
    # la entrega ocurrió 48 h después de crear la orden
    orden = session.get(Orden, ids[0])
    entrega = session.query(HistorialEtapa).filter_by(orden_id=ids[0], etapa="entregada").one()
    entrega.creado_en = orden.creado_en + timedelta(hours=48)
    session.commit()
    r = api.get("/metricas").json()
    assert {e["etapa"]: e["ordenes"] for e in r["ordenes_por_etapa"]} == {
        "en_cola": 1, "en_produccion": 1, "terminada": 0, "entregada": 1,
    }
    assert r["ordenes_total"] == 3 and r["ordenes_con_acuse_pendiente"] == 1
    assert r["horas_promedio_entrega"] == 48.0
