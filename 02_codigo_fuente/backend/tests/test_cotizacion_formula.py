from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import Precio, Producto, TarifaMaterial
from app.seed import CATALOGO, TARIFAS, cargar

HOY = date.today()


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def joya(session):
    """Anillo de 4 g con 78 USD de mano de obra, ofrecido en oro 18k y plata."""
    producto = Producto(
        nombre="Anillo de prueba",
        categoria="Anillos",
        peso_gramos=Decimal("4.00"),
        mano_obra=Decimal("78.00"),
    )
    session.add(producto)
    session.commit()
    session.add_all(
        [
            Precio(producto_id=producto.id, material="oro", quilataje="18k",
                   precio=Decimal("1.00"), vigente_desde=HOY),
            Precio(producto_id=producto.id, material="plata", quilataje=None,
                   precio=Decimal("1.00"), vigente_desde=HOY),
            TarifaMaterial(material="oro", quilataje="18k",
                           precio_gramo=Decimal("95.00"), vigente_desde=HOY),
            TarifaMaterial(material="oro", quilataje="14k",
                           precio_gramo=Decimal("74.00"), vigente_desde=HOY),
            TarifaMaterial(material="plata", quilataje=None,
                           precio_gramo=Decimal("1.60"), vigente_desde=HOY),
        ]
    )
    session.commit()
    return producto.id


def cotizar(api, producto_id, **params):
    return api.get(f"/productos/{producto_id}/cotizacion", params=params)


def test_oro_se_calcula_con_peso_por_precio_del_gramo_mas_mano_de_obra(api, joya):
    datos = cotizar(api, joya, material="oro", quilataje="18k").json()
    assert datos["metodo"] == "formula"
    assert Decimal(datos["peso_gramos"]) == Decimal("4.00")
    assert Decimal(datos["precio_gramo"]) == Decimal("95.00")
    assert Decimal(datos["costo_material"]) == Decimal("380.00")
    assert Decimal(datos["mano_obra"]) == Decimal("78.00")
    assert Decimal(datos["precio"]) == Decimal("458.00")


def test_en_plata_pesa_mas_la_mano_de_obra_que_el_material(api, joya):
    datos = cotizar(api, joya, material="plata").json()
    assert Decimal(datos["precio"]) == Decimal("84.40")
    assert Decimal(datos["mano_obra"]) > Decimal(datos["costo_material"])


def test_el_precio_no_es_el_de_la_tabla_fija(api, joya):
    # La tabla `precios` dice 1.00; la cotización sale de la fórmula.
    assert Decimal(cotizar(api, joya, material="oro", quilataje="18k").json()["precio"]) > 1


def test_si_cambia_el_precio_del_gramo_cambia_la_cotizacion(api, session, joya):
    antes = Decimal(cotizar(api, joya, material="oro", quilataje="18k").json()["precio"])
    session.add(
        TarifaMaterial(material="oro", quilataje="18k",
                       precio_gramo=Decimal("100.00"), vigente_desde=HOY + timedelta(days=0))
    )
    session.commit()
    despues = Decimal(cotizar(api, joya, material="oro", quilataje="18k").json()["precio"])
    assert despues - antes == Decimal("20.00")  # 4 g x 5 USD de diferencia


def test_ignora_tarifas_con_vigencia_futura(api, session, joya):
    session.add(
        TarifaMaterial(material="oro", quilataje="18k",
                       precio_gramo=Decimal("500.00"), vigente_desde=HOY + timedelta(days=5))
    )
    session.commit()
    datos = cotizar(api, joya, material="oro", quilataje="18k").json()
    assert Decimal(datos["precio_gramo"]) == Decimal("95.00")


def test_sin_tarifa_vigente_usa_el_precio_de_la_tabla(api, session, joya):
    for t in session.scalars(select(TarifaMaterial).where(TarifaMaterial.material == "plata")):
        session.delete(t)
    session.commit()
    datos = cotizar(api, joya, material="plata").json()
    assert datos["metodo"] == "tabla"
    assert Decimal(datos["precio"]) == Decimal("1.00")
    assert datos["peso_gramos"] is None


def test_una_tarifa_no_ofrece_combinaciones_que_la_pieza_no_tiene(api, joya):
    # Existe tarifa de oro 14k, pero este anillo no se ofrece en 14k.
    assert cotizar(api, joya, material="oro", quilataje="14k").status_code == 422


def test_el_listado_y_el_detalle_usan_la_misma_formula(api, joya):
    lista = api.get("/productos").json()
    detalle = api.get(f"/productos/{joya}").json()
    assert lista[0]["precios"] == detalle["precios"]
    assert Decimal(detalle["precio_desde"]) == Decimal("84.40")
    oro = [p for p in detalle["precios"] if p["material"] == "oro"][0]
    assert Decimal(oro["precio"]) == Decimal("458.00")


def test_redondea_a_centavos(api, session):
    producto = Producto(nombre="Dije", categoria="Dijes",
                        peso_gramos=Decimal("1.23"), mano_obra=Decimal("10.00"))
    session.add(producto)
    session.commit()
    session.add_all(
        [
            Precio(producto_id=producto.id, material="oro", quilataje="18k",
                   precio=Decimal("1"), vigente_desde=HOY),
            TarifaMaterial(material="oro", quilataje="18k",
                           precio_gramo=Decimal("95.55"), vigente_desde=HOY),
        ]
    )
    session.commit()
    datos = cotizar(api, producto.id, material="oro", quilataje="18k").json()
    assert Decimal(datos["costo_material"]) == Decimal("117.53")  # 117.5265
    assert Decimal(datos["precio"]) == Decimal("127.53")


def test_seed_carga_tarifas_y_completa_piezas_ya_existentes(session):
    primero = CATALOGO[0]
    existente = Producto(nombre=primero[0], categoria=primero[1])
    editado = Producto(
        nombre=CATALOGO[1][0], categoria=CATALOGO[1][1],
        peso_gramos=Decimal("9.99"), mano_obra=Decimal("1.00"),
    )
    session.add_all([existente, editado])
    session.commit()

    cargar(session)
    session.refresh(existente)
    session.refresh(editado)
    assert existente.peso_gramos == Decimal(primero[3])
    assert existente.mano_obra == Decimal(primero[4])
    assert editado.peso_gramos == Decimal("9.99")  # no se pisa lo ya editado
    assert len(session.scalars(select(TarifaMaterial)).all()) == len(TARIFAS)

    cargar(session)  # repetible
    assert len(session.scalars(select(TarifaMaterial)).all()) == len(TARIFAS)


def test_todo_el_catalogo_sembrado_se_cotiza_con_formula(api, session):
    cargar(session)
    for producto in session.scalars(select(Producto)):
        for p in api.get(f"/productos/{producto.id}").json()["precios"]:
            params = {"material": p["material"]}
            if "quilataje" in p and p["quilataje"]:
                params["quilataje"] = p["quilataje"]
            datos = cotizar(api, producto.id, **params).json()
            assert datos["metodo"] == "formula"
            assert Decimal(datos["precio"]) == Decimal(p["precio"])
