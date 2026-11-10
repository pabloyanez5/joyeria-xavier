import pytest
from fastapi.testclient import TestClient

import logging

from sqlalchemy import select

from app import webhook
from app.agente.rutas import get_proveedor
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.models import Conversacion, Mensaje

client = TestClient(app)


def test_verificacion_ok(monkeypatch):
    monkeypatch.setenv("META_VERIFY_TOKEN", "secreto")
    r = client.get(
        "/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "secreto",
            "hub.challenge": "12345",
        },
    )
    assert r.status_code == 200
    assert r.text == "12345"


def test_verificacion_token_invalido(monkeypatch):
    monkeypatch.setenv("META_VERIFY_TOKEN", "secreto")
    r = client.get(
        "/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "otro",
            "hub.challenge": "12345",
        },
    )
    assert r.status_code == 403


@pytest.fixture
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


PAYLOAD_WHATSAPP = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "contacts": [
                            {"wa_id": "593999111222", "profile": {"name": "Ana"}}
                        ],
                        "messages": [{"from": "593999111222", "type": "text"}],
                    }
                }
            ]
        }
    ],
}


def test_post_whatsapp_registra_cliente_una_sola_vez(api):
    r1 = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r1.status_code == 200
    assert r1.json()["clientes_nuevos"] == 1
    r2 = api.post("/webhook/meta", json=PAYLOAD_WHATSAPP)
    assert r2.json()["clientes_nuevos"] == 0


def test_post_messenger_registra_cliente(api):
    payload = {
        "object": "page",
        "entry": [
            {"messaging": [{"sender": {"id": "777"}, "message": {"text": "hola"}}]}
        ],
    }
    r = api.post("/webhook/meta", json=payload)
    assert r.json()["clientes_nuevos"] == 1


def test_post_objeto_desconocido_no_registra_nada(api):
    r = api.post("/webhook/meta", json={"object": "otra_cosa", "entry": []})
    assert r.status_code == 200
    assert r.json()["clientes_nuevos"] == 0

def _payload_texto(texto, wamid="wamid.1", tipo="text"):
    mensaje = {"from": "593999111222", "id": wamid, "type": tipo}
    if tipo == "text":
        mensaje["text"] = {"body": texto}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"wa_id": "593999111222", "profile": {"name": "Ana"}}
                            ],
                            "messages": [mensaje],
                        }
                    }
                ]
            }
        ],
    }


def test_post_con_texto_lo_atiende_el_agente_y_guarda_la_conversacion(api, session, caplog):
    with caplog.at_level(logging.INFO, logger="joyeria.webhook"):
        r = api.post("/webhook/meta", json=_payload_texto("hola"))
    assert r.json() == {"status": "ok", "clientes_nuevos": 1, "respuestas": 1, "enviadas": 0}
    assert len(session.scalars(select(Conversacion)).all()) == 1
    direcciones = [m.direccion for m in session.scalars(select(Mensaje).order_by(Mensaje.id))]
    assert direcciones == ["entrante", "saliente"]
    registro = caplog.text
    assert "Respuesta del agente a whatsapp ***1222" in registro
    assert "593999111222" not in registro


def test_post_repetido_de_meta_no_se_responde_dos_veces(api, session):
    api.post("/webhook/meta", json=_payload_texto("hola", wamid="wamid.9"))
    r = api.post("/webhook/meta", json=_payload_texto("hola", wamid="wamid.9"))
    assert r.json()["respuestas"] == 0
    assert len(session.scalars(select(Mensaje)).all()) == 2


def test_post_sin_texto_solo_registra_al_cliente(api, session):
    r = api.post("/webhook/meta", json=_payload_texto("", tipo="image"))
    assert r.json() == {"status": "ok", "clientes_nuevos": 1, "respuestas": 0, "enviadas": 0}
    assert session.scalars(select(Mensaje)).all() == []


def test_si_el_agente_falla_igual_se_responde_200(api, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(webhook, "atender_mensaje", falla)
    r = api.post("/webhook/meta", json=_payload_texto("hola"))
    assert r.status_code == 200
    assert r.json()["respuestas"] == 0
