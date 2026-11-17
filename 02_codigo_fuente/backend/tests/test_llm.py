import io
import json
import urllib.error

import pytest

from app.agente import llm
from app.agente.llm import ErrorLLM, Gemini, proveedor_desde_entorno


class RespuestaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _respuesta(datos):
    return RespuestaFalsa(json.dumps(datos).encode("utf-8"))


def test_gemini_extrae_el_texto_y_envia_la_clave_en_el_encabezado(monkeypatch):
    enviado = {}

    def falso_urlopen(peticion, timeout):
        enviado["clave"] = peticion.get_header("X-goog-api-key")
        enviado["cuerpo"] = json.loads(peticion.data)
        enviado["url"] = peticion.full_url
        return _respuesta({"candidates": [{"content": {"parts": [{"text": "cotizar"}]}}]})

    monkeypatch.setattr(llm.urllib.request, "urlopen", falso_urlopen)
    texto = Gemini("clave-de-prueba", "gemini-2.5-flash").generar("sistema", "hola")
    assert texto == "cotizar"
    assert enviado["clave"] == "clave-de-prueba"
    assert "clave-de-prueba" not in enviado["url"]
    assert enviado["cuerpo"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_gemini_convierte_errores_de_red_en_errorllm(monkeypatch):
    def falla(peticion, timeout):
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(llm.urllib.request, "urlopen", falla)
    with pytest.raises(ErrorLLM):
        Gemini("x").generar("s", "u")


def test_gemini_respuesta_sin_candidatos_da_errorllm(monkeypatch):
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda p, timeout: _respuesta({}))
    with pytest.raises(ErrorLLM):
        Gemini("x").generar("s", "u")


def test_proveedor_desde_entorno(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert proveedor_desde_entorno() is None
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    proveedor = proveedor_desde_entorno()
    assert isinstance(proveedor, Gemini)
    assert proveedor.modelo == "gemini-2.5-flash-lite"


def test_gemini_incluye_el_motivo_de_los_errores_http(monkeypatch):
    def falla(peticion, timeout):
        raise urllib.error.HTTPError(
            peticion.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"error": "cupo agotado"}')
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", falla)
    with pytest.raises(ErrorLLM, match="429.*cupo agotado"):
        Gemini("x").generar("s", "u")
