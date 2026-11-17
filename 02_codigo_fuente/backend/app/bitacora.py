"""Bitácora de la API: a la consola y, si hay LOG_DIR, también a un archivo que rota.

Los logs de Docker se pierden cada vez que el deploy recrea el contenedor; el archivo vive en un
volumen y sobrevive, así se puede revisar después por qué el agente respondió con las reglas.
Los teléfonos y claves ya llegan enmascarados desde quien escribe el log.
"""
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"
TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB por archivo
ARCHIVOS = 5  # api.log y 5 anteriores: unos 30 MB como máximo

_CLAVE_DE_GOOGLE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")


def sin_claves(texto: str) -> str:
    """Quita de un texto (por ejemplo, el mensaje de un error) cualquier clave de Google."""
    return _CLAVE_DE_GOOGLE.sub("AIza***", texto)


class Formato(logging.Formatter):
    """Formato de la bitácora; tapa las claves también dentro de las trazas de error."""

    def __init__(self):
        super().__init__(FORMATO)

    def format(self, record: logging.LogRecord) -> str:
        return sin_claves(super().format(record))


def configurar() -> None:
    registro = logging.getLogger("joyeria")
    if getattr(registro, "_configurada", False):
        return
    registro.setLevel(logging.INFO)
    formato = Formato()
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    registro.addHandler(consola)
    carpeta = os.getenv("LOG_DIR", "").strip()
    if carpeta:
        try:
            Path(carpeta).mkdir(parents=True, exist_ok=True)
            archivo = RotatingFileHandler(
                Path(carpeta) / "api.log",
                maxBytes=TAMANO_MAXIMO,
                backupCount=ARCHIVOS,
                encoding="utf-8",
            )
            archivo.setFormatter(formato)
            registro.addHandler(archivo)
        except OSError:
            registro.warning("No se pudo abrir la bitácora en %s; sigue solo en consola", carpeta)
    registro._configurada = True
