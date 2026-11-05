"""Proveedores de modelo de lenguaje intercambiables (sin dependencias extra)."""
import json
import os
import urllib.error
import urllib.request


class ErrorLLM(Exception):
    """El proveedor no pudo responder (red, tiempo agotado, respuesta rara)."""


class ProveedorLLM:
    def generar(self, sistema: str, usuario: str) -> str:
        raise NotImplementedError


class Gemini(ProveedorLLM):
    def __init__(self, api_key: str, modelo: str = "gemini-3.1-flash-lite", timeout: float = 4.0):
        self.api_key = api_key
        self.modelo = modelo
        self.timeout = timeout

    def generar(self, sistema: str, usuario: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.modelo}:generateContent"
        )
        config = {"temperature": 0, "maxOutputTokens": 1024}
        # Los modelos 2.5 Flash piensan antes de responder; para un chat
        # corto lo apagamos y así se mantiene el tiempo de respuesta bajo.
        if "2.5" in self.modelo and "pro" not in self.modelo:
            config["thinkingConfig"] = {"thinkingBudget": 0}
        cuerpo = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": usuario}]}],
            "generationConfig": config,
        }
        peticion = urllib.request.Request(
            url,
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                datos = json.load(respuesta)
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise ErrorLLM(f"Error {e.code} del modelo: {detalle}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise ErrorLLM(f"No se pudo consultar el modelo: {e}") from e
        try:
            return datos["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise ErrorLLM("Respuesta inesperada del modelo") from e


def proveedor_desde_entorno() -> ProveedorLLM | None:
    """Gemini si hay GEMINI_API_KEY; si no, None (el agente usa solo reglas)."""
    clave = os.getenv("GEMINI_API_KEY", "").strip()
    if not clave:
        return None
    return Gemini(clave, os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
