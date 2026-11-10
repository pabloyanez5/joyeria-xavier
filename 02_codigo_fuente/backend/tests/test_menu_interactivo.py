import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import meta_envio
from app.agente.rutas import get_proveedor
from app.agente.servicio import atender_mensaje
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.mensajes import Boton, Fila, Saliente, botones, cortar, imagen, lista
from app.meta_envio import Enviador, EnviadorMeta, ErrorMeta
from app.models import Cliente, Producto
from app.seed import cargar
from app.webhook import extraer_mensajes, get_enviador

WEB = "http://sitio.test"
MEDIA = "https://fotos.test"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("WEB_URL", WEB)
    monkeypatch.setenv("MEDIA_URL", MEDIA)


@pytest.fixture
def catalogo(session):
    cargar(session)


def _enviar(session, cache, texto="hola", accion=None, id_canal="593999"):
    return atender_mensaje(
        session, cache, "whatsapp", id_canal, texto, accion=accion, proveedor=None
    )


# --- mensajes con formato ---

def test_cortar_respeta_el_largo_y_deja_puntos_suspensivos():
    assert cortar("Argolla de matrimonio diamantada", 24) == "Argolla de matrimonio d…"
    assert len(cortar("Argolla de matrimonio diamantada", 24)) == 24
    assert cortar("Anillo", 24) == "Anillo"


def test_la_version_plana_lista_las_opciones():
    plano = botones("¿Qué hacemos?", [Boton("a", "Cotizar"), Boton("b", "Asesor")]).plano()
    assert plano == "¿Qué hacemos?\n• Cotizar\n• Asesor"
    plano = lista("Elige", [Fila("1", "Anillo", "Desde $85.00")]).plano()
    assert "• Anillo · Desde $85.00" in plano
    assert imagen("https://x/y.png", "Pie").plano() == "Pie\nhttps://x/y.png"


def test_maximo_de_tres_botones_y_diez_filas():
    assert len(botones("x", [Boton(str(i), "b") for i in range(5)]).botones) == 3
    assert len(lista("x", [Fila(str(i), "f") for i in range(15)]).filas) == 10


# --- cuerpo que se manda a Meta ---

def test_cuerpo_de_botones():
    cuerpo = EnviadorMeta._cuerpo("593", botones("Hola", [Boton("menu:cotizar", "Cotizar una joya muy larga")]))
    assert cuerpo["type"] == "interactive"
    assert cuerpo["interactive"]["type"] == "button"
    boton = cuerpo["interactive"]["action"]["buttons"][0]["reply"]
    assert boton["id"] == "menu:cotizar"
    assert len(boton["title"]) <= 20


def test_cuerpo_de_lista_recorta_titulos_y_descripciones():
    fila = Fila("prod:1", "Argolla de matrimonio diamantada", "d" * 100)
    cuerpo = EnviadorMeta._cuerpo("593", lista("Elige", [fila], etiqueta="Ver joyas"))
    accion = cuerpo["interactive"]["action"]
    assert cuerpo["interactive"]["type"] == "list"
    assert accion["button"] == "Ver joyas"
    fila_meta = accion["sections"][0]["rows"][0]
    assert len(fila_meta["title"]) <= 24 and len(fila_meta["description"]) <= 72


def test_cuerpo_de_imagen_y_de_texto():
    cuerpo = EnviadorMeta._cuerpo("593", imagen("https://x/y.png", "Pie"))
    assert cuerpo["type"] == "image"
    assert cuerpo["image"] == {"link": "https://x/y.png", "caption": "Pie"}
    cuerpo = EnviadorMeta._cuerpo("593", Saliente("texto", "Hola"))
    assert cuerpo["type"] == "text" and cuerpo["text"]["body"] == "Hola"


def test_el_enviador_manda_un_mensaje_con_formato(monkeypatch):
    capturado = {}

    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def falso(peticion, timeout):
        capturado["cuerpo"] = json.loads(peticion.data)
        return Respuesta()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    ok = EnviadorMeta("tok", "1").enviar_saliente(
        "whatsapp", "593", botones("Hola", [Boton("a", "A")])
    )
    assert ok is True and capturado["cuerpo"]["interactive"]["type"] == "button"


def test_un_canal_sin_soporte_recibe_la_version_plana():
    class Solo(Enviador):
        def __init__(self):
            self.textos = []

        def enviar(self, canal, destinatario, texto):
            self.textos.append(texto)
            return True

    e = Solo()
    e.enviar_saliente("instagram", "1", botones("Hola", [Boton("a", "Cotizar")]))
    assert e.textos == ["Hola\n• Cotizar"]


# --- lectura de lo que toca el cliente ---

def _payload_interactivo(tipo, id_, titulo, wamid="wamid.i1"):
    respuesta = {"id": id_, "title": titulo}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "593999111222", "profile": {"name": "Ana"}}],
                            "messages": [
                                {
                                    "from": "593999111222",
                                    "id": wamid,
                                    "type": "interactive",
                                    "interactive": {"type": tipo, tipo: respuesta},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def test_lee_la_respuesta_de_un_boton_y_de_una_lista():
    boton = extraer_mensajes(_payload_interactivo("button_reply", "menu:asesor", "Hablar con asesor"))
    assert (boton[0].accion, boton[0].texto) == ("menu:asesor", "Hablar con asesor")
    fila = extraer_mensajes(_payload_interactivo("list_reply", "prod:3", "Pulsera tejida"))
    assert (fila[0].accion, fila[0].texto) == ("prod:3", "Pulsera tejida")


# --- el flujo del agente ---

def test_el_saludo_ofrece_tres_botones(session, cache, catalogo):
    r = _enviar(session, cache, "hola")
    assert "asistente virtual" in r.texto  # el texto plano de siempre no cambia
    assert [m.tipo for m in r.mensajes] == ["botones"]
    assert [b.id for b in r.mensajes[0].botones] == ["menu:cotizar", "menu:catalogo", "menu:asesor"]


def test_cotizar_sin_contexto_muestra_las_categorias(session, cache, catalogo):
    r = _enviar(session, cache, "quiero cotizar")
    lista_ = r.mensajes[0]
    assert lista_.tipo == "lista"
    assert [f.id for f in lista_.filas] == [
        "cat:Anillos", "cat:Aretes", "cat:Argollas", "cat:Cadenas", "cat:Dijes", "cat:Pulseras",
    ]


def test_cotizar_un_anillo_muestra_los_anillos_con_su_precio(session, cache, catalogo):
    r = _enviar(session, cache, "quiero cotizar un anillo")
    lista_ = r.mensajes[0]
    assert lista_.tipo == "lista" and "anillos" in lista_.texto
    assert len(lista_.filas) == 3
    assert all(f.id.startswith("prod:") for f in lista_.filas)
    assert lista_.filas[0].descripcion == "Desde $84.40"  # plata: 4 g x $1.60 + $78
    assert "categoria=Anillos" in r.texto  # la versión de texto sigue llevando el enlace


def test_elegir_una_categoria_la_recuerda_y_lista_sus_joyas(session, cache, catalogo):
    r = _enviar(session, cache, "Cadenas", accion="cat:Cadenas")
    assert [f.titulo for f in r.mensajes[0].filas] == ["Cadena cubana", "Cadena veneciana"]
    cliente = session.scalar(select(Cliente))
    assert cliente.contexto_cualificacion["categoria"] == "Cadenas"


def test_elegir_una_joya_manda_la_foto_y_las_opciones(session, cache, catalogo):
    producto = session.scalar(select(Producto).where(Producto.nombre == "Anillo solitario clásico"))
    r = _enviar(session, cache, producto.nombre, accion=f"prod:{producto.id}")
    foto, opciones = r.mensajes
    assert foto.tipo == "imagen"
    assert foto.imagen_url == f"{MEDIA}/img/anillos.png"
    assert "Anillo solitario clásico" in foto.texto and "Desde $84.40" in foto.texto
    assert [b.id for b in opciones.botones] == [
        f"precios:{producto.id}", "menu:catalogo", "menu:asesor",
    ]


def test_la_foto_usa_la_url_de_la_web_si_no_hay_url_de_fotos(session, cache, catalogo, monkeypatch):
    monkeypatch.delenv("MEDIA_URL")
    producto = session.scalar(select(Producto))
    r = _enviar(session, cache, "x", accion=f"prod:{producto.id}")
    assert r.mensajes[0].imagen_url.startswith(f"{WEB}/img/")


def test_una_joya_sin_foto_se_muestra_solo_con_botones(session, cache, catalogo):
    producto = session.scalar(select(Producto))
    producto.imagen_url = None
    session.commit()
    r = _enviar(session, cache, "x", accion=f"prod:{producto.id}")
    assert [m.tipo for m in r.mensajes] == ["botones"]
    assert producto.nombre in r.mensajes[0].texto


def test_los_precios_se_explican_con_la_formula(session, cache, catalogo):
    producto = session.scalar(select(Producto).where(Producto.nombre == "Anillo solitario clásico"))
    r = _enviar(session, cache, "Ver precios", accion=f"precios:{producto.id}")
    detalle, opciones = r.mensajes
    assert "Oro 18k: *$458.00* (4 g × $95.00/g + $78.00 de mano de obra)" in detalle.texto
    assert "Plata: *$84.40*" in detalle.texto
    assert f"{WEB}/?categoria=Anillos" in detalle.texto
    assert "asesor confirma" in detalle.texto
    assert [b.id for b in opciones.botones] == ["menu:catalogo", "menu:asesor"]


def test_pedir_un_asesor_con_el_boton_escala_y_el_agente_calla(session, cache, catalogo):
    r = _enviar(session, cache, "Hablar con asesor", accion="menu:asesor")
    assert r.escalada and "asesor" in r.texto
    callado = _enviar(session, cache, "hola")
    assert callado.texto is None and callado.mensajes is None


def test_una_accion_desconocida_vuelve_al_menu(session, cache, catalogo):
    r = _enviar(session, cache, "x", accion="cosa:rara")
    assert r.mensajes[0].tipo == "botones"
    r = _enviar(session, cache, "x", accion="prod:99999", id_canal="593111")
    assert "ya no está disponible" in r.mensajes[0].texto


def test_los_mensajes_del_flujo_quedan_guardados(session, cache, catalogo):
    from app.models import Mensaje

    _enviar(session, cache, "Cadenas", accion="cat:Cadenas")
    guardados = [(m.direccion, m.contenido) for m in session.scalars(select(Mensaje).order_by(Mensaje.id))]
    assert guardados[0] == ("entrante", "Cadenas")
    assert guardados[1][0] == "saliente" and "Cadena cubana" in guardados[1][1]


# --- de punta a punta por el webhook ---

class EnviadorRegistra(Enviador):
    def __init__(self, falla_en=()):
        self.salientes = []
        self.falla_en = falla_en

    def enviar(self, canal, destinatario, texto):
        raise AssertionError("debía usar enviar_saliente")

    def enviar_saliente(self, canal, destinatario, saliente):
        if saliente.tipo in self.falla_en:
            raise ErrorMeta("Meta respondió 400")
        self.salientes.append(saliente)
        return True


@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_tocar_una_joya_envia_la_foto_y_los_botones(api, catalogo, session):
    falso = EnviadorRegistra()
    app.dependency_overrides[get_enviador] = lambda: falso
    producto = session.scalar(select(Producto))
    r = api.post(
        "/webhook/meta",
        json=_payload_interactivo("list_reply", f"prod:{producto.id}", producto.nombre),
    )
    assert r.json()["enviadas"] == 2
    assert [s.tipo for s in falso.salientes] == ["imagen", "botones"]


def test_si_meta_no_puede_traer_la_foto_se_manda_su_descripcion(api, catalogo, session):
    falso = EnviadorRegistra(falla_en=("imagen",))
    app.dependency_overrides[get_enviador] = lambda: falso
    producto = session.scalar(select(Producto))
    r = api.post(
        "/webhook/meta",
        json=_payload_interactivo("list_reply", f"prod:{producto.id}", producto.nombre),
    )
    assert r.status_code == 200
    assert [s.tipo for s in falso.salientes] == ["texto", "botones"]
    assert producto.nombre in falso.salientes[0].texto


def test_si_meta_rechaza_la_lista_igual_se_responde_200(api, catalogo):
    falso = EnviadorRegistra(falla_en=("lista",))
    app.dependency_overrides[get_enviador] = lambda: falso
    r = api.post("/webhook/meta", json=_payload_interactivo("button_reply", "menu:cotizar", "Cotizar"))
    assert r.status_code == 200 and r.json()["enviadas"] == 0


def test_si_falla_un_mensaje_no_se_manda_el_siguiente(api, catalogo, session):
    falso = EnviadorRegistra(falla_en=("texto",))
    app.dependency_overrides[get_enviador] = lambda: falso
    producto = session.scalar(select(Producto))
    r = api.post(
        "/webhook/meta",
        json=_payload_interactivo("button_reply", f"precios:{producto.id}", "Ver precios"),
    )
    assert r.status_code == 200 and r.json()["enviadas"] == 0
    assert falso.salientes == []
