from fastapi.testclient import TestClient

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