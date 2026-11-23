"""JOY-73 · Instagram: un mensaje a la cuenta de la joyería crea al cliente con canal Instagram
y el agente responde por el mismo canal, con el webhook firmado."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import meta_envio
from app.agente.rutas import get_proveedor
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.meta_envio import Enviador, EnviadorMeta
from app.models import Cliente, Conversacion, Mensaje
from app.webhook import get_enviador

IGSID = "17841400000005242"  # id del cliente en Instagram (lo asigna Meta)
CUENTA = "17841499999999999"  # la cuenta joyeriaxavier.test


def mensaje_de_instagram(texto="Hola", mid="aWdfZAG1faXRlbToxOk1FU1NBR0VfSUQ", **extra) -> dict:
    """Así llega un DM de Instagram al webhook (objeto «instagram», como Messenger)."""
    return {
        "object": "instagram",
        "entry": [
            {
                "id": CUENTA,
                "time": 1795470938000,
                "messaging": [
                    {
                        "sender": {"id": IGSID},
                        "recipient": {"id": CUENTA},
                        "timestamp": 1795470937000,
                        "message": {"mid": mid, "text": texto, **extra},
                    }
                ],
            }
        ],
    }


class EnviadorInstagram(Enviador):
    """Guarda lo que se enviaría y devuelve el nombre de perfil que daría Meta."""

    def __init__(self, nombre="Pablo Yánez"):
        self.nombre = nombre
        self.enviados = []
        self.consultas = 0

    def enviar(self, canal, destinatario, texto):
        self.enviados.append((canal, destinatario, texto))
        return True

    def nombre_de_perfil(self, canal, id_canal):
        self.consultas += 1
        return self.nombre


@pytest.fixture
def enviador():
    return EnviadorInstagram()


@pytest.fixture
def api(session, cache, enviador, monkeypatch):
    for clave in ("META_APP_SECRET", "META_INSTAGRAM_APP_SECRET"):
        monkeypatch.delenv(clave, raising=False)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    app.dependency_overrides[get_enviador] = lambda: enviador
    yield TestClient(app)
    app.dependency_overrides.clear()


def firmar(secreto: str, cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


def publicar(api, payload, secreto=None, firma=None):
    cuerpo = json.dumps(payload).encode()
    cabeceras = {"Content-Type": "application/json"}
    if secreto or firma:
        cabeceras["X-Hub-Signature-256"] = firma or firmar(secreto, cuerpo)
    return api.post("/webhook/meta", content=cuerpo, headers=cabeceras)


def test_un_dm_crea_al_cliente_de_instagram_y_el_agente_responde_por_instagram(api, session, enviador):
    r = publicar(api, mensaje_de_instagram("Hola"))
    assert r.status_code == 200
    assert r.json()["clientes_nuevos"] == 1 and r.json()["enviadas"] == 1

    cliente = session.scalar(select(Cliente))
    assert (cliente.canal, cliente.id_canal) == ("instagram", IGSID)
    assert cliente.nombre_perfil == "Pablo Yánez"

    (canal, destinatario, texto) = enviador.enviados[0]
    assert (canal, destinatario) == ("instagram", IGSID) and texto

    conversacion = session.scalar(select(Conversacion))
    assert conversacion.canal == "instagram"
    mensajes = session.scalars(select(Mensaje).order_by(Mensaje.id)).all()
    assert [m.direccion for m in mensajes] == ["entrante", "saliente"]


def test_el_segundo_dm_sigue_en_la_misma_conversacion_sin_volver_a_consultar_el_nombre(api, session, enviador):
    publicar(api, mensaje_de_instagram("Hola", mid="m1"))
    publicar(api, mensaje_de_instagram("busco aretes de oro", mid="m2"))
    assert len(session.scalars(select(Cliente)).all()) == 1
    assert len(session.scalars(select(Conversacion)).all()) == 1
    assert enviador.consultas == 1  # el nombre se pide a Meta solo la primera vez


def test_un_dm_repetido_por_meta_no_se_responde_dos_veces(api, enviador):
    publicar(api, mensaje_de_instagram("Hola", mid="mismo"))
    publicar(api, mensaje_de_instagram("Hola", mid="mismo"))
    assert len(enviador.enviados) == 1


def test_la_copia_de_nuestra_propia_respuesta_no_se_atiende(api, session, enviador):
    # Instagram reenvía al webhook lo que manda la cuenta («is_echo»): no es un cliente.
    publicar(api, mensaje_de_instagram("¡Hola! Soy el asistente", is_echo=True))
    assert session.scalar(select(Cliente)) is None and enviador.enviados == []


def test_los_avisos_de_leido_no_crean_clientes(api, session, enviador):
    payload = {
        "object": "instagram",
        "entry": [{"id": CUENTA, "messaging": [{"sender": {"id": IGSID}, "read": {"mid": "m1"}}]}],
    }
    assert publicar(api, payload).status_code == 200
    assert session.scalar(select(Cliente)) is None and enviador.enviados == []


def test_tocar_una_opcion_en_instagram_llega_como_accion(api, session, enviador):
    publicar(api, mensaje_de_instagram("Hola", mid="m1"))
    publicar(api, mensaje_de_instagram("Aretes", mid="m2", quick_reply={"payload": "cat:Aretes"}))
    assert len(enviador.enviados) >= 2  # respondió también a la opción tocada
    ultima = session.scalars(select(Mensaje).order_by(Mensaje.id.desc())).first()
    assert ultima.origen == "menu"  # la resolvió el menú, igual que un botón de WhatsApp


# --- firma del webhook ---

def test_con_la_firma_de_la_app_se_acepta(api, monkeypatch, enviador):
    monkeypatch.setenv("META_APP_SECRET", "clave-app")
    assert publicar(api, mensaje_de_instagram(), secreto="clave-app").status_code == 200
    assert len(enviador.enviados) == 1


def test_sin_firma_o_con_firma_falsa_se_rechaza(api, monkeypatch, session):
    monkeypatch.setenv("META_APP_SECRET", "clave-app")
    assert publicar(api, mensaje_de_instagram()).status_code == 403
    assert publicar(api, mensaje_de_instagram(), firma="sha256=falsa").status_code == 403
    assert publicar(api, mensaje_de_instagram(), secreto="otra-clave").status_code == 403
    assert session.scalar(select(Cliente)) is None


def test_tambien_acepta_la_clave_de_la_app_de_instagram(api, monkeypatch):
    # Con el inicio de sesión de Instagram, Meta firma con la clave de la app de Instagram.
    monkeypatch.setenv("META_APP_SECRET", "clave-app")
    monkeypatch.setenv("META_INSTAGRAM_APP_SECRET", "clave-instagram")
    assert publicar(api, mensaje_de_instagram(), secreto="clave-instagram").status_code == 200
    assert publicar(api, mensaje_de_instagram(mid="m2"), secreto="clave-app").status_code == 200


# --- nombre de perfil en Instagram ---

class Respuesta:
    def __init__(self, datos):
        self.cuerpo = json.dumps(datos).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo


@pytest.mark.parametrize(
    "datos, esperado",
    [
        ({"name": "Pablo Yánez", "username": "pablo.yz"}, "Pablo Yánez"),
        ({"username": "pablo.yz"}, "pablo.yz"),  # sin nombre público: el usuario
        ({}, None),
    ],
)
def test_en_instagram_pide_nombre_y_usuario(monkeypatch, datos, esperado):
    pedido = {}

    def falso(peticion, timeout):
        pedido["url"] = peticion.full_url
        return Respuesta(datos)

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    envio = EnviadorMeta("t", "1", "v23.0", page_id="9", page_token="p")
    assert envio.nombre_de_perfil("instagram", IGSID) == esperado
    assert pedido["url"].endswith(f"/{IGSID}?fields=name,username")
