import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.agente.rutas import get_proveedor
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.meta_envio import Enviador, ErrorMeta
from app.webhook import get_enviador

from tests.test_webhook import _payload_texto

PAYLOAD_WHATSAPP = _payload_texto("hola", wamid="wamid.envio")


class EnviadorFalso(Enviador):
    def __init__(self, falla=False):
        self.enviados = []
        self.falla = falla

    def enviar(self, canal, destinatario, texto):
        if self.falla:
            raise ErrorMeta("Meta respondió 400")
        self.enviados.append((canal, destinatario, texto))
        return True


@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def con_enviador(enviador):
    app.dependency_overrides[get_enviador] = lambda: enviador


def test_la_respuesta_del_agente_se_envia_por_whatsapp(api):
    falso = EnviadorFalso()
    con_enviador(falso)
    r = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r.status_code == 200
    assert r.json()["enviadas"] == 1
    assert len(falso.enviados) == 1
    canal, destinatario, texto = falso.enviados[0]
    assert canal == "whatsapp"
    assert destinatario == PAYLOAD_WHATSAPP["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
    assert "asistente virtual" in texto or texto


def test_un_mensaje_repetido_de_meta_no_se_envia_dos_veces(api):
    falso = EnviadorFalso()
    con_enviador(falso)
    api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    r = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r.status_code == 200
    assert len(falso.enviados) == 1


def test_si_meta_rechaza_el_envio_igual_se_responde_200(api):
    con_enviador(EnviadorFalso(falla=True))
    r = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r.status_code == 200
    assert r.json()["enviadas"] == 0
    assert r.json()["respuestas"] == 1


def test_sin_credenciales_no_se_envia_nada(api):
    con_enviador(None)
    r = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r.status_code == 200
    assert r.json()["enviadas"] == 0


def firmar(secreto, cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


def test_con_secreto_una_firma_incorrecta_se_rechaza(api, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "s3creto")
    con_enviador(None)
    cuerpo = json.dumps(PAYLOAD_WHATSAPP).encode()
    r = api.post(
        "/webhook/meta",
        content=cuerpo,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=malo"},
    )
    assert r.status_code == 403


def test_con_secreto_sin_firma_se_rechaza(api, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "s3creto")
    con_enviador(None)
    r = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r.status_code == 403


def test_con_secreto_una_firma_correcta_se_acepta(api, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "s3creto")
    falso = EnviadorFalso()
    con_enviador(falso)
    cuerpo = json.dumps(PAYLOAD_WHATSAPP).encode()
    r = api.post(
        "/webhook/meta",
        content=cuerpo,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": firmar("s3creto", cuerpo),
        },
    )
    assert r.status_code == 200
    assert len(falso.enviados) == 1
