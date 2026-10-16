import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app

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
def api(session):
    app.dependency_overrides[get_session] = lambda: session
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