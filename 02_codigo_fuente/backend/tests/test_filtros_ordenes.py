"""JOY-83: filtros en el tablero de órdenes e historial cronológico de cada orden."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Cliente, Orden, Usuario
from app.webhook import get_enviador
from tests.conftest import datos_de_orden, entrar_como, verificar


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_enviador, None)


@pytest.fixture
def datos(session):
    ana = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana Pérez")
    luis = Cliente(canal="messenger", id_canal="psid-2", nombre_perfil="Luis Mora")
    asesor = Usuario(nombre="Carla", email="carla@x.com", rol="asesor")
    taller = Usuario(nombre="Marta", email="marta@x.com", rol="taller")
    session.add_all([ana, luis, asesor, taller])
    session.commit()
    return {"ana": ana, "luis": luis, "asesor": asesor, "taller": taller}


def _crear(api, cliente, descripcion, **extra):
    return api.post(
        "/ordenes",
        json=datos_de_orden(
            **{"cliente_id": cliente.id, "descripcion": descripcion,
               "nombre_completo": cliente.nombre_perfil, **extra}
        ),
    ).json()


def _ids(respuesta) -> list[int]:
    assert respuesta.status_code == 200, respuesta.text
    return [o["id"] for o in respuesta.json()]


def test_busca_por_codigo_de_orden_con_o_sin_prefijo(api, datos):
    a = _crear(api, datos["ana"], "Aretes de oro")
    _crear(api, datos["luis"], "Cadena de plata")
    for texto in (a["codigo"], a["codigo"].lower(), str(a["id"]), f"OP{a['id']}"):
        assert _ids(api.get("/ordenes", params={"q": texto})) == [a["id"]], texto


def test_busca_por_codigo_de_pedido(api, datos):
    pedido = api.post(
        "/ordenes/pedido",
        json={
            "cliente_id": datos["ana"].id, "nombre_completo": "Ana Pérez", "telefono": "0991234567",
            "joyas": [
                {k: v for k, v in datos_de_orden(descripcion=d).items() if k not in ("nombre_completo", "telefono")}
                for d in ("Aretes", "Cadena")
            ],
        },
    ).json()
    _crear(api, datos["luis"], "Anillo")
    r = api.get("/ordenes", params={"q": pedido["codigo"]})
    assert sorted(_ids(r)) == sorted(o["id"] for o in pedido["ordenes"])


def test_busca_por_cliente_o_por_detalle_sin_importar_mayusculas(api, datos):
    a = _crear(api, datos["ana"], "Aretes de oro 18k")
    c = _crear(api, datos["luis"], "Cadena de PLATA veneciana")
    assert _ids(api.get("/ordenes", params={"q": "ana pé"})) == [a["id"]]
    assert _ids(api.get("/ordenes", params={"q": "plata"})) == [c["id"]]
    assert _ids(api.get("/ordenes", params={"q": "MORA"})) == [c["id"]]
    assert _ids(api.get("/ordenes", params={"q": "nada que ver"})) == []


def test_filtra_por_rango_de_fechas_inclusive(api, session, datos):
    viejas = [_crear(api, datos["ana"], f"Joya {n}") for n in range(3)]
    hoy = datetime.now(timezone.utc)
    for dias, orden in zip((20, 10, 0), viejas):
        session.get(Orden, orden["id"]).creado_en = hoy - timedelta(days=dias)
    session.commit()
    dia = lambda d: (hoy - timedelta(days=d)).date().isoformat()  # noqa: E731
    assert _ids(api.get("/ordenes", params={"desde": dia(15)})) == [viejas[2]["id"], viejas[1]["id"]]
    assert _ids(api.get("/ordenes", params={"hasta": dia(10)})) == [viejas[1]["id"], viejas[0]["id"]]
    assert _ids(api.get("/ordenes", params={"desde": dia(10), "hasta": dia(10)})) == [viejas[1]["id"]]
    assert api.get("/ordenes", params={"desde": dia(1), "hasta": dia(5)}).status_code == 422


def test_los_filtros_se_combinan(api, datos):
    a1 = verificar(api, _crear(api, datos["ana"], "Aretes de oro"))
    _crear(api, datos["ana"], "Aretes de plata")  # por verificar
    _crear(api, datos["luis"], "Aretes de oro")
    r = api.get("/ordenes", params={"q": "ana", "etapa": "en_cola"})
    assert _ids(r) == [a1["id"]]


def test_funciona_con_mas_de_doscientas_ordenes(api, session, datos):
    for n in range(210):
        session.add(Orden(cliente_id=datos["ana"].id, descripcion=f"Joya {n}", etapa_actual="en_cola"))
    session.commit()
    todas = _ids(api.get("/ordenes"))
    assert len(todas) == 210 and todas == sorted(todas, reverse=True)
    assert len(_ids(api.get("/ordenes", params={"q": "Joya 20"}))) == 11  # 20 y 200..209


def test_el_historial_es_cronologico_con_fecha_y_responsable(api, datos):
    entrar_como(datos["asesor"])
    orden = verificar(api, _crear(api, datos["ana"], "Aretes de oro"))
    entrar_como(datos["taller"])
    for etapa in ("en_produccion", "terminada", "entregada"):
        api.post(f"/ordenes/{orden['id']}/etapa", json={"etapa": etapa, "avisar_al_cliente": False})
    historial = api.get(f"/ordenes/{orden['id']}/historial").json()
    assert [(h["etapa"], h["usuario"]) for h in historial] == [
        ("por_verificar", "Carla"), ("en_cola", "Carla"), ("en_produccion", "Marta"),
        ("terminada", "Marta"), ("entregada", "Marta"),
    ]
    fechas = [h["creado_en"] for h in historial]
    assert all(fechas) and fechas == sorted(fechas)
