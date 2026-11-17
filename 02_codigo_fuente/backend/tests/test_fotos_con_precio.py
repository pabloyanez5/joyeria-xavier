"""JOY-82 (parte 2): el cliente ve la foto y el precio de las joyas antes de elegir."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agente import menu
from app.agente.rutas import get_proveedor
from app.agente.servicio import atender_mensaje
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.meta_envio import EnviadorMeta
from app.mensajes import Boton, tarjeta
from app.models import Producto
from app.seed import cargar
from app.webhook import get_enviador
from tests.test_menu_interactivo import EnviadorRegistra, _payload_interactivo

WEB = "http://sitio.test"
MEDIA = "https://fotos.test"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("WEB_URL", WEB)
    monkeypatch.setenv("MEDIA_URL", MEDIA)


@pytest.fixture
def catalogo(session):
    cargar(session)


def _con_fotos_propias(session, categoria):
    """Cada joya con su foto, como quedará cuando la joyería suba las reales."""
    for p in session.scalars(select(Producto).where(Producto.categoria == categoria)):
        p.imagen_url = f"/img/{p.id}.jpg"
    session.commit()


# --- la tarjeta: foto, nombre, precio y botones en un solo mensaje ---

def test_la_tarjeta_va_a_whatsapp_como_botones_con_foto_de_cabecera():
    t = tarjeta("https://fotos.test/a.jpg", "*Aretes*\nDesde $41.20", [Boton("prod:1", "Ver detalle")])
    cuerpo = EnviadorMeta._cuerpo("593999", t)
    assert cuerpo["type"] == "interactive"
    interactivo = cuerpo["interactive"]
    assert interactivo["type"] == "button"
    assert interactivo["header"] == {"type": "image", "image": {"link": "https://fotos.test/a.jpg"}}
    assert interactivo["body"]["text"] == "*Aretes*\nDesde $41.20"
    assert interactivo["action"]["buttons"][0]["reply"] == {"id": "prod:1", "title": "Ver detalle"}


def test_en_canales_sin_botones_la_tarjeta_llega_como_texto_con_el_enlace_de_la_foto():
    t = tarjeta("https://fotos.test/a.jpg", "*Aretes*\nDesde $41.20", [Boton("prod:1", "Ver detalle")])
    assert t.plano() == "*Aretes*\nDesde $41.20\nhttps://fotos.test/a.jpg\n• Ver detalle"


# --- qué fotos se muestran ---

def test_cada_joya_trae_su_foto_su_precio_y_dos_botones(session, catalogo):
    _con_fotos_propias(session, "Anillos")
    fotos = menu.fotos_de_productos(session, "Anillos", MEDIA)
    assert len(fotos) == 3
    primera = fotos[0]
    producto = session.scalar(select(Producto).where(Producto.nombre == "Anillo solitario clásico"))
    assert primera.imagen_url == f"{MEDIA}/img/{producto.id}.jpg"
    assert primera.texto == "*Anillo solitario clásico*\nDesde $84.40"
    assert [b.id for b in primera.botones] == [f"prod:{producto.id}", f"precios:{producto.id}"]


def test_no_se_mandan_mas_de_tres_fotos(session, catalogo):
    for n in range(4):
        session.add(Producto(nombre=f"Anillo extra {n}", categoria="Anillos", activo=True))
    session.commit()
    _con_fotos_propias(session, "Anillos")
    assert len(menu.fotos_de_productos(session, "Anillos", MEDIA)) == menu.MAX_FOTOS


def test_una_foto_compartida_por_varias_joyas_se_manda_una_sola_vez(session, catalogo):
    # Las fotos provisionales son una por categoría: repetirla tres veces no ayuda a elegir.
    fotos = menu.fotos_de_productos(session, "Anillos", MEDIA)
    assert len(fotos) == 1 and fotos[0].imagen_url == f"{MEDIA}/img/anillos.png"


def test_las_joyas_sin_foto_o_inactivas_no_tienen_tarjeta(session, catalogo):
    for p in session.scalars(select(Producto).where(Producto.categoria == "Cadenas")):
        p.imagen_url = None
    session.commit()
    assert menu.fotos_de_productos(session, "Cadenas", MEDIA) == []
    assert menu.fotos_de_productos(session, "Categoría que no existe", MEDIA) == []


# --- dónde aparecen ---

def test_elegir_una_categoria_muestra_la_lista_y_luego_las_fotos(session, cache, catalogo):
    _con_fotos_propias(session, "Cadenas")
    r = atender_mensaje(session, cache, "whatsapp", "593999", "Cadenas", accion="cat:Cadenas")
    assert [m.tipo for m in r.mensajes] == ["lista", "tarjeta", "tarjeta"]
    assert [m.texto.split("\n")[0] for m in r.mensajes[1:]] == ["*Cadena cubana*", "*Cadena veneciana*"]


def test_en_modo_reglas_las_fotos_van_entre_la_lista_y_el_enlace(session, cache, catalogo):
    r = atender_mensaje(session, cache, "whatsapp", "593999", "quiero ver aretes")
    assert [m.tipo for m in r.mensajes] == ["lista", "tarjeta", "texto"]
    assert r.mensajes[1].imagen_url == f"{MEDIA}/img/aretes.png"


def test_cuando_el_agente_muestra_opciones_tambien_van_las_fotos(session, cache, catalogo):
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage

    from tests.test_agente_langchain import llamada, modelo

    _con_fotos_propias(session, "Cadenas")
    m = modelo(
        llamada("mostrar_opciones", categoria="Cadenas"),
        AIMessage("Mira estas cadenas."),
    )
    r = atender_mensaje(session, cache, "whatsapp", "593999", "qué cadenas tienen?", proveedor=None, modelo=m)
    assert [x.tipo for x in r.mensajes] == ["lista", "tarjeta", "tarjeta"]
    assert r.mensajes[0].texto == "Mira estas cadenas."


def test_el_panel_guarda_tambien_las_fotos_que_se_mandaron(session, cache, catalogo):
    from app.models import Mensaje

    atender_mensaje(session, cache, "whatsapp", "593999", "Aretes", accion="cat:Aretes")
    guardado = session.scalars(
        select(Mensaje).where(Mensaje.direccion == "saliente").order_by(Mensaje.id.desc())
    ).first()
    assert f"{MEDIA}/img/aretes.png" in guardado.contenido and "Ver detalle" in guardado.contenido


# --- si Meta no puede traer la foto ---

@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_si_meta_no_trae_la_foto_la_tarjeta_llega_sin_foto_pero_con_botones(api, catalogo):
    falso = EnviadorRegistra(falla_en=("tarjeta",))
    app.dependency_overrides[get_enviador] = lambda: falso
    r = api.post("/webhook/meta", json=_payload_interactivo("list_reply", "cat:Aretes", "Aretes"))
    assert r.status_code == 200
    assert [s.tipo for s in falso.salientes] == ["lista", "botones"]
    assert falso.salientes[1].texto.startswith("*Aretes")
    assert [b.titulo for b in falso.salientes[1].botones] == ["Ver detalle", "Ver precios"]
