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

# Ocasiones (texto normalizado -> cómo se guarda). JOY-94: sin modelo, el motor de reglas también
# las reconoce y sigue la conversación en vez de responder «no entendí».
OCASIONES = {
    "aniversario": "aniversario",
    "cumpleanos": "cumpleaños",
    "boda": "boda",
    "matrimonio": "boda",
    "compromiso": "compromiso",
    "pedida de mano": "compromiso",
    "graduacion": "graduación",
    "bautizo": "bautizo",
    "primera comunion": "primera comunión",
    "dia de la madre": "día de la madre",
    "san valentin": "San Valentín",
    "navidad": "Navidad",
    "quince anos": "quince años",
    "quinceanera": "quince años",
    "regalo": "regalo",
}
# Presupuesto: un monto con $, USD o dólares, o después de «presupuesto» / «hasta».
_PRESUPUESTO = (
    re.compile(r"\$\s?(\d{2,6})\b"),
    re.compile(r"\b(\d{2,6})\s?(?:\$|usd\b|dolares\b|dolar\b)"),
    re.compile(r"\bpresupuesto (?:es |de |de unos |de hasta )?(\d{2,6})\b"),
    re.compile(r"\bhasta (?:unos )?(\d{2,6})\b"),
)

PATRON_NOMBRE = re.compile(
    r"(?:me llamo|mi nombre es)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,30})", re.IGNORECASE
)


@dataclass
class Datos:
    contexto: dict = field(default_factory=dict)
    nombre: str | None = None
    talla: str | None = None


def normalizar_con_signos(texto: str) -> str:
    """Como `normalizar` (minúsculas, sin tildes ni signos) pero conserva el $ de los montos."""
    return normalizar(texto.replace("$", " dolarsigno ")).replace("dolarsigno", "$")


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


def ocasion_y_presupuesto(texto: str) -> dict:
    """Ocasión y presupuesto que el cliente menciona (JOY-94).

    Solo lo usa el motor de reglas cuando el modelo no responde; con el modelo, estos datos los
    anota la herramienta de preferencias, que sabe a qué joya corresponden.
    """
    datos = {}
    con_espacios = f" {normalizar(texto)} "
    for frase, ocasion in OCASIONES.items():
        if f" {frase} " in con_espacios:
            datos["ocasion"] = ocasion
            break
    con_signos = normalizar_con_signos(texto)
    for patron in _PRESUPUESTO:
        monto = patron.search(con_signos)
        if monto:
            datos["presupuesto"] = f"${int(monto.group(1))}"
            break
    return datos
