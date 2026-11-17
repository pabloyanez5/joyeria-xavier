"""Datos de cualificación que el cliente va mencionando (JOY-29)."""
import re
from dataclasses import dataclass, field

from app.agente.intenciones import normalizar

# Las categorías coinciden con las del catálogo.
CATEGORIAS = {
    "anillo": "Anillos", "anillos": "Anillos",
    "argolla": "Argollas", "argollas": "Argollas",
    "alianza": "Argollas", "alianzas": "Argollas",
    "cadena": "Cadenas", "cadenas": "Cadenas",
    "pulsera": "Pulseras", "pulseras": "Pulseras",
    "esclava": "Pulseras", "esclavas": "Pulseras",
    "arete": "Aretes", "aretes": "Aretes", "aro": "Aretes", "aros": "Aretes",
    "dije": "Dijes", "dijes": "Dijes", "colgante": "Dijes", "colgantes": "Dijes",
}
MATERIALES = {"oro": "oro", "plata": "plata"}

PATRON_NOMBRE = re.compile(
    r"(?:me llamo|mi nombre es)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,30})", re.IGNORECASE
)


@dataclass
class Datos:
    contexto: dict = field(default_factory=dict)
    nombre: str | None = None
    talla: str | None = None


def extraer(texto: str) -> Datos:
    """Saca lo que el mensaje diga sobre categoría, material, quilataje, talla y nombre."""
    limpio = normalizar(texto)
    datos = Datos()
    for palabra in limpio.split():
        if palabra in CATEGORIAS and "categoria" not in datos.contexto:
            datos.contexto["categoria"] = CATEGORIAS[palabra]
        if palabra in MATERIALES and "material" not in datos.contexto:
            datos.contexto["material"] = MATERIALES[palabra]
    quilataje = re.search(r"\b(14|18) ?(?:k|quilates)\b", limpio)
    if quilataje:
        datos.contexto["quilataje"] = f"{quilataje.group(1)}k"
    talla = re.search(r"\btalla (\d{1,2})\b", limpio)
    if talla:
        datos.talla = talla.group(1)
    nombre = PATRON_NOMBRE.search(texto)
    if nombre:
        datos.nombre = nombre.group(1).capitalize()
    return datos
