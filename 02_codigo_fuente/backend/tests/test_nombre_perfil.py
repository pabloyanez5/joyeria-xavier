import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import meta_envio
from app.agente.rutas import get_proveedor
from app.cache import get_cache
from app.clientes import registrar_cliente
from app.db import get_session
from app.main import app
from app.meta_envio import Enviador, EnviadorMeta
from app.models import Cliente
from app.webhook import get_enviador


class RespuestaConNombre:
    def __init__(self, cuerpo=None):
        self.cuerpo = cuerpo or json.dumps({"name": "Ana Pérez", "id": "PSID1"}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo


# --- consulta del nombre a Meta ---

def test_consulta_el_nombre_en_messenger_con_el_token_de_la_pagina(monkeypatch):
    capturado = {}

    def falso(peticion, timeout):
        capturado["url"] = peticion.full_url
        capturado["cabeceras"] = dict(peticion.header_items())
        capturado["timeout"] = timeout
        return RespuestaConNombre()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    envio = EnviadorMeta("tok", "1", "v23.0", page_id="9", page_token="pagetok")
    assert envio.nombre_de_perfil("messenger", "PSID1") == "Ana Pérez"
    assert capturado["url"] == "https://graph.facebook.com/v23.0/PSID1?fields=name"
    assert capturado["cabeceras"]["Authorization"] == "Bearer pagetok"
    assert capturado["timeout"] <= 3


def test_no_consulta_en_whatsapp_ni_sin_token_de_pagina(monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("no debía llamar a Meta")

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", no_debe_llamarse)
    con_pagina = EnviadorMeta("tok", "1", page_id="9", page_token="pagetok")
    assert con_pagina.nombre_de_perfil("whatsapp", "593999") is None
    assert EnviadorMeta("tok", "1").nombre_de_perfil("messenger", "PSID1") is None


@pytest.mark.parametrize("falla", [OSError("sin red"), ValueError("raro")])
def test_si_la_consulta_falla_devuelve_none_sin_romper(monkeypatch, falla):
    def falso(peticion, timeout):
        raise falla

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    envio = EnviadorMeta("tok", "1", page_id="9", page_token="pagetok")
    assert envio.nombre_de_perfil("messenger", "PSID1") is None


def test_si_meta_no_trae_nombre_devuelve_none(monkeypatch):
    monkeypatch.setattr(
        meta_envio.urllib.request, "urlopen", lambda p, timeout: RespuestaConNombre(b"{}")
    )
    envio = EnviadorMeta("tok", "1", page_id="9", page_token="pagetok")
    assert envio.nombre_de_perfil("messenger", "PSID1") is None


# --- el nombre llega al cliente ---

class EnviadorConNombre(Enviador):
    def __init__(self, nombre="Ana Pérez"):
        self.nombre = nombre
        self.consultas = 0

    def enviar(self, canal, destinatario, texto):
        return True

    def nombre_de_perfil(self, canal, id_canal):
        self.consultas += 1
        return self.nombre


def _messenger(texto="hola", mid="m1"):
    return {
        "object": "page",
        "entry": [
            {"messaging": [{"sender": {"id": "PSID1"}, "message": {"mid": mid, "text": texto}}]}
        ],
    }


@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_un_cliente_nuevo_de_messenger_queda_con_su_nombre(api, session):
    app.dependency_overrides[get_enviador] = lambda: EnviadorConNombre()
    assert api.post("/webhook/meta", json=_messenger()).status_code == 200
    assert session.scalar(select(Cliente)).nombre_perfil == "Ana Pérez"


def test_el_nombre_se_consulta_solo_la_primera_vez(api):
    falso = EnviadorConNombre()
    app.dependency_overrides[get_enviador] = lambda: falso
    api.post("/webhook/meta", json=_messenger("hola", "m1"))
    api.post("/webhook/meta", json=_messenger("busco argollas", "m2"))
    assert falso.consultas == 1


def test_si_no_hay_nombre_el_cliente_se_registra_igual(api, session):
    app.dependency_overrides[get_enviador] = lambda: EnviadorConNombre(nombre=None)
    assert api.post("/webhook/meta", json=_messenger()).status_code == 200
    assert session.scalar(select(Cliente)).nombre_perfil is None


def test_un_cliente_sin_nombre_lo_recibe_cuando_llega(session):
    cliente, _ = registrar_cliente(session, "messenger", "PSID9")
    assert cliente.nombre_perfil is None
    cliente, creado = registrar_cliente(session, "messenger", "PSID9", "Luis Mora")
    assert not creado and cliente.nombre_perfil == "Luis Mora"


def test_un_nombre_ya_guardado_no_se_pisa(session):
    registrar_cliente(session, "messenger", "PSID9", "Luis Mora")
    cliente, _ = registrar_cliente(session, "messenger", "PSID9", "Otro Nombre")
    assert cliente.nombre_perfil == "Luis Mora"
