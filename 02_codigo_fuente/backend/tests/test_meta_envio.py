import io
import json
import urllib.error

import pytest

from app import meta_envio
from app.meta_envio import EnviadorMeta, ErrorMeta, enviador_desde_entorno


class RespuestaFalsa:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"{}"


def test_arma_la_peticion_de_whatsapp(monkeypatch):
    capturado = {}

    def falso(peticion, timeout):
        capturado["url"] = peticion.full_url
        capturado["cabeceras"] = dict(peticion.header_items())
        capturado["cuerpo"] = json.loads(peticion.data)
        capturado["timeout"] = timeout
        return RespuestaFalsa()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    ok = EnviadorMeta("tok", "123456", "v23.0").enviar("whatsapp", "593999111222", "Hola")
    assert ok is True
    assert capturado["url"] == "https://graph.facebook.com/v23.0/123456/messages"
    assert capturado["cabeceras"]["Authorization"] == "Bearer tok"
    assert capturado["cuerpo"]["to"] == "593999111222"
    assert capturado["cuerpo"]["messaging_product"] == "whatsapp"
    assert capturado["cuerpo"]["text"]["body"] == "Hola"
    assert capturado["timeout"] == 10


def test_sin_pagina_configurada_no_se_envia_por_messenger_ni_instagram(monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("no debía llamar a Meta")

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", no_debe_llamarse)
    assert EnviadorMeta("tok", "1").enviar("instagram", "abc", "Hola") is False
    assert EnviadorMeta("tok", "1").enviar("messenger", "abc", "Hola") is False
    assert EnviadorMeta("tok", "1").enviar("telegram", "abc", "Hola") is False


@pytest.mark.parametrize("canal", ["messenger", "instagram"])
def test_arma_la_peticion_de_messenger_e_instagram(monkeypatch, canal):
    capturado = {}

    def falso(peticion, timeout):
        capturado["url"] = peticion.full_url
        capturado["cabeceras"] = dict(peticion.header_items())
        capturado["cuerpo"] = json.loads(peticion.data)
        return RespuestaFalsa()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    envio = EnviadorMeta("tok-wa", "111", "v23.0", page_id="999", page_token="tok-pag")
    assert envio.enviar(canal, "psid-77", "Hola") is True
    assert capturado["url"] == "https://graph.facebook.com/v23.0/999/messages"
    assert capturado["cabeceras"]["Authorization"] == "Bearer tok-pag"
    assert capturado["cuerpo"] == {
        "recipient": {"id": "psid-77"},
        "message": {"text": "Hola"},
        "messaging_type": "RESPONSE",
    }


def test_instagram_corta_el_texto_al_maximo_permitido(monkeypatch):
    capturado = {}

    def falso(peticion, timeout):
        capturado["cuerpo"] = json.loads(peticion.data)
        return RespuestaFalsa()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    envio = EnviadorMeta("t", "1", page_id="9", page_token="p")
    envio.enviar("instagram", "x", "a" * 3000)
    assert len(capturado["cuerpo"]["message"]["text"]) == 1000


def test_error_de_la_pagina_se_informa_como_errormeta(monkeypatch):
    def falso(peticion, timeout):
        raise urllib.error.HTTPError(peticion.full_url, 403, "No", {}, io.BytesIO(b'{"error":"permiso"}'))

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    with pytest.raises(ErrorMeta, match="403"):
        EnviadorMeta("t", "1", page_id="9", page_token="p").enviar("messenger", "x", "Hola")


def test_el_entorno_incluye_la_pagina_si_esta_configurada(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("META_PAGE_ID", "999")
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "tok-pag")
    envio = enviador_desde_entorno()
    assert envio.page_id == "999" and envio.page_token == "tok-pag"


def test_error_http_de_meta_se_convierte_en_errormeta(monkeypatch):
    def falso(peticion, timeout):
        raise urllib.error.HTTPError(
            peticion.full_url, 400, "Bad", {}, io.BytesIO(b'{"error":"x"}')
        )

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    with pytest.raises(ErrorMeta, match="400"):
        EnviadorMeta("tok", "1").enviar("whatsapp", "593", "Hola")


def test_error_de_red_se_convierte_en_errormeta(monkeypatch):
    def falso(peticion, timeout):
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    with pytest.raises(ErrorMeta):
        EnviadorMeta("tok", "1").enviar("whatsapp", "593", "Hola")


def test_reintenta_si_la_red_falla_un_momento(monkeypatch):
    llamadas = []

    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def falso(peticion, timeout):
        llamadas.append(1)
        if len(llamadas) < 3:
            raise urllib.error.URLError("[Errno 101] Network is unreachable")
        return Respuesta()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    assert EnviadorMeta("tok", "1").enviar("whatsapp", "593", "Hola") is True
    assert len(llamadas) == 3


def test_se_rinde_tras_los_intentos_configurados(monkeypatch):
    llamadas = []

    def falso(peticion, timeout):
        llamadas.append(1)
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    with pytest.raises(ErrorMeta, match="No se pudo contactar"):
        EnviadorMeta("tok", "1", intentos=2).enviar("whatsapp", "593", "Hola")
    assert len(llamadas) == 2


def test_un_error_http_no_se_reintenta(monkeypatch):
    llamadas = []

    def falso(peticion, timeout):
        llamadas.append(1)
        raise urllib.error.HTTPError(peticion.full_url, 401, "No", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    with pytest.raises(ErrorMeta, match="401"):
        EnviadorMeta("tok", "1").enviar("whatsapp", "593", "Hola")
    assert len(llamadas) == 1


def test_el_token_no_aparece_en_el_mensaje_de_error(monkeypatch):
    def falso(peticion, timeout):
        raise urllib.error.HTTPError(peticion.full_url, 401, "No", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    with pytest.raises(ErrorMeta) as e:
        EnviadorMeta("TOKEN-SECRETO", "1").enviar("whatsapp", "593", "Hola")
    assert "TOKEN-SECRETO" not in str(e.value)


def test_desde_entorno_sin_credenciales_es_none():
    assert enviador_desde_entorno() is None


def test_desde_entorno_con_credenciales(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "999")
    monkeypatch.setenv("META_API_VERSION", "v25.0")
    e = enviador_desde_entorno()
    assert isinstance(e, EnviadorMeta)
    assert e._url() == "https://graph.facebook.com/v25.0/999/messages"


def test_version_por_defecto(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "999")
    monkeypatch.setenv("META_API_VERSION", "")
    assert enviador_desde_entorno().version == meta_envio.VERSION_POR_DEFECTO
