"""JOY-90: lista de órdenes por páginas, ordenable, para alto volumen (retroalimentación del jurado)."""
from datetime import date, timedelta

import pytest

from app.models import Cliente, Orden
from tests.conftest import entrar_como
from tests.test_etapas import api, datos  # noqa: F401


def _sembrar(session, datos, cuantas):
    """Órdenes con fecha de entrega distinta (la 1 entrega primero) y etapas alternadas."""
    etapas = ["por_verificar", "en_cola", "en_produccion", "terminada", "entregada", "cancelada"]
    ordenes = []
    for n in range(1, cuantas + 1):
        orden = Orden(
            cliente_id=datos["cliente"].id,
            descripcion=f"Joya {n:03d}",
            etapa_actual=etapas[n % len(etapas)],
            fecha_entrega_cliente=date(2026, 12, 1) + timedelta(days=n),
        )
        session.add(orden)
        ordenes.append(orden)
    session.commit()
    return ordenes


def _pagina(api, **params):
    r = api.get("/ordenes/pagina", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_nunca_trae_mas_que_el_tamano_de_la_pagina(api, session, datos):
    _sembrar(session, datos, 60)
    primera = _pagina(api)
    assert len(primera["ordenes"]) == 25
    assert (primera["total"], primera["paginas"], primera["pagina"]) == (60, 3, 1)
    ultima = _pagina(api, pagina=3)
    assert len(ultima["ordenes"]) == 10


def test_las_paginas_no_repiten_ni_saltan_ordenes(api, session, datos):
    sembradas = _sembrar(session, datos, 60)
    vistas = []
    for pagina in (1, 2, 3):
        vistas += [o["id"] for o in _pagina(api, pagina=pagina, orden="codigo", direccion="asc")["ordenes"]]
    assert vistas == [o.id for o in sembradas]


@pytest.mark.parametrize("por_pagina", [25, 50, 100])
def test_se_puede_elegir_el_tamano(api, session, datos, por_pagina):
    _sembrar(session, datos, 120)
    assert len(_pagina(api, por_pagina=por_pagina)["ordenes"]) == por_pagina


def test_un_tamano_no_permitido_se_rechaza(api):
    r = api.get("/ordenes/pagina", params={"por_pagina": 1000})
    assert r.status_code == 422 and "25, 50 o 100" in r.json()["detail"]


def test_el_total_respeta_los_filtros(api, session, datos):
    _sembrar(session, datos, 60)
    r = _pagina(api, etapa="cancelada")
    assert r["total"] == 10 and all(o["etapa_actual"] == "cancelada" for o in r["ordenes"])
    r = _pagina(api, q="Joya 05")
    assert r["total"] == 10  # Joya 050 … Joya 059


def test_ordenar_por_fecha_de_entrega(api, session, datos):
    sembradas = _sembrar(session, datos, 30)
    asc = _pagina(api, orden="entrega", direccion="asc")["ordenes"]
    assert asc[0]["id"] == sembradas[0].id
    desc = _pagina(api, orden="entrega", direccion="desc")["ordenes"]
    assert desc[0]["id"] == sembradas[-1].id


def test_las_ordenes_sin_fecha_van_al_final(api, session, datos):
    _sembrar(session, datos, 3)
    vieja = Orden(cliente_id=datos["cliente"].id, descripcion="Sin fecha", etapa_actual="en_cola")
    session.add(vieja)
    session.commit()
    for direccion in ("asc", "desc"):
        assert _pagina(api, orden="entrega", direccion=direccion)["ordenes"][-1]["id"] == vieja.id


def test_ordenar_por_etapa_sigue_el_proceso(api, session, datos):
    _sembrar(session, datos, 12)
    etapas = [o["etapa_actual"] for o in _pagina(api, orden="etapa", direccion="asc")["ordenes"]]
    proceso = ["por_verificar", "en_cola", "en_produccion", "terminada", "entregada", "cancelada"]
    assert etapas == sorted(etapas, key=proceso.index)


def test_ordenar_por_cliente(api, session, datos):
    zoila = Cliente(canal="whatsapp", id_canal="593222", nombre_perfil="Zoila Ruiz")
    andres = Cliente(canal="whatsapp", id_canal="593333", nombre_perfil="andrés León")
    session.add_all([zoila, andres])
    session.commit()
    for cliente in (zoila, andres):
        session.add(Orden(cliente_id=cliente.id, descripcion="Anillo", etapa_actual="en_cola"))
    session.commit()
    nombres = [o["cliente"] for o in _pagina(api, orden="cliente", direccion="asc")["ordenes"]]
    assert nombres == ["andrés León", "Zoila Ruiz"]


def test_una_pagina_vacia_igual_informa_el_total(api, session, datos):
    _sembrar(session, datos, 5)
    r = _pagina(api, pagina=9)
    assert r["ordenes"] == [] and r["total"] == 5 and r["paginas"] == 1


@pytest.mark.parametrize(
    "params, mensaje",
    [({"orden": "precio"}, "orden"), ({"direccion": "arriba"}, "dirección"), ({"pagina": 0}, None)],
)
def test_parametros_invalidos(api, params, mensaje):
    r = api.get("/ordenes/pagina", params=params)
    assert r.status_code == 422
    if mensaje:
        assert mensaje in r.json()["detail"]


def test_el_taller_ve_la_lista_y_direccion_no(api, session, datos):
    _sembrar(session, datos, 3)
    entrar_como(datos["taller"])
    assert api.get("/ordenes/pagina").status_code == 200
    from app.models import Usuario

    jefa = Usuario(nombre="Dir", email="dir@x.com", rol="direccion")
    session.add(jefa)
    session.commit()
    entrar_como(jefa)
    assert api.get("/ordenes/pagina").status_code == 403
