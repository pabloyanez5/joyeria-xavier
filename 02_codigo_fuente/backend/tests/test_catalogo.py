from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Precio, Producto


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def catalogo(session):
    hoy = date.today()
    anillo = Producto(nombre="Anillo solitario", categoria="Anillos", descripcion="Clásico")
    cadena = Producto(nombre="Cadena cubana", categoria="Cadenas")
    viejo = Producto(nombre="Descontinuado", categoria="Anillos", activo=False)
    session.add_all([anillo, cadena, viejo])
    session.commit()
    session.add_all(
        [
            Precio(producto_id=anillo.id, material="oro", quilataje="18k",
                   precio=Decimal("400.00"), vigente_desde=hoy - timedelta(days=30)),
            Precio(producto_id=anillo.id, material="oro", quilataje="18k",
                   precio=Decimal("450.00"), vigente_desde=hoy - timedelta(days=1)),
            Precio(producto_id=anillo.id, material="oro", quilataje="18k",
                   precio=Decimal("999.00"), vigente_desde=hoy + timedelta(days=10)),
            Precio(producto_id=anillo.id, material="plata", quilataje=None,
                   precio=Decimal("80.00"), vigente_desde=hoy),
            Precio(producto_id=cadena.id, material="oro", quilataje="14k",
                   precio=Decimal("700.00"), vigente_desde=hoy),
        ]
    )
    session.commit()
    return {"anillo": anillo.id, "cadena": cadena.id, "viejo": viejo.id}


def test_lista_solo_productos_activos(api, catalogo):
    nombres = [p["nombre"] for p in api.get("/productos").json()]
    assert nombres == ["Anillo solitario", "Cadena cubana"]


def test_usa_el_precio_vigente_mas_reciente_y_ignora_futuros(api, catalogo):
    anillo = api.get(f"/productos/{catalogo['anillo']}").json()
    oro = [x for x in anillo["precios"] if x["material"] == "oro"]
    assert len(oro) == 1
    assert Decimal(oro[0]["precio"]) == Decimal("450")
    assert Decimal(anillo["precio_desde"]) == Decimal("80")


def test_filtra_por_categoria_sin_importar_mayusculas(api, catalogo):
    r = api.get("/productos", params={"categoria": "cadenas"}).json()
    assert [p["nombre"] for p in r] == ["Cadena cubana"]


def test_filtra_por_material_y_precio_maximo(api, catalogo):
    r = api.get("/productos", params={"material": "oro", "precio_max": 500}).json()
    assert [p["nombre"] for p in r] == ["Anillo solitario"]
    assert [x["material"] for x in r[0]["precios"]] == ["oro"]


def test_busca_por_texto(api, catalogo):
    r = api.get("/productos", params={"q": "cubana"}).json()
    assert [p["nombre"] for p in r] == ["Cadena cubana"]


def test_categorias_sin_repetir_ni_inactivos(api, catalogo):
    assert api.get("/productos/categorias").json() == ["Anillos", "Cadenas"]


def test_detalle_inexistente_o_inactivo_da_404(api, catalogo):
    assert api.get("/productos/9999").status_code == 404
    assert api.get(f"/productos/{catalogo['viejo']}").status_code == 404