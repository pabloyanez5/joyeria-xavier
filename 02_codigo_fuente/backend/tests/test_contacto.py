from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VARIABLES = ("JOYERIA_WHATSAPP", "JOYERIA_INSTAGRAM", "JOYERIA_MESSENGER")


def test_sin_numero_no_ofrece_un_whatsapp_que_no_llega_a_nadie(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    assert client.get("/contacto", params={"mensaje": "Hola"}).json() == []


def test_solo_whatsapp_si_es_lo_unico_configurado(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("JOYERIA_WHATSAPP", "+1 555 000 1234")
    canales = client.get("/contacto", params={"mensaje": "Hola"}).json()
    assert [c["enlace"] for c in canales] == ["https://wa.me/15550001234?text=Hola"]


def test_incluye_numero_y_canales_configurados(monkeypatch):
    monkeypatch.setenv("JOYERIA_WHATSAPP", "+59300000000")
    monkeypatch.setenv("JOYERIA_INSTAGRAM", "cuenta_demo")
    monkeypatch.setenv("JOYERIA_MESSENGER", "pagina_demo")
    canales = client.get("/contacto", params={"mensaje": "Hola mundo"}).json()
    enlaces = {c["canal"]: c["enlace"] for c in canales}
    assert enlaces["whatsapp"] == "https://wa.me/59300000000?text=Hola%20mundo"
    assert enlaces["instagram"] == "https://ig.me/m/cuenta_demo"
    assert enlaces["messenger"] == "https://m.me/pagina_demo"


def test_codifica_el_mensaje(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("JOYERIA_WHATSAPP", "593000")
    canales = client.get("/contacto", params={"mensaje": "oro 24k & talla 9"}).json()
    assert "%26" in canales[0]["enlace"]