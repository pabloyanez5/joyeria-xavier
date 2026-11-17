"""Clasificación de la intención de un mensaje: reglas + modelo opcional."""
import re
import unicodedata

from app.agente.llm import ErrorLLM, ProveedorLLM

INTENCIONES = (
    "saludo",
    "cotizar",
    "catalogo",
    "estado_pedido",
    "asesor",
    "despedida",
    "otro",
)

# El orden importa: la primera intención que coincide gana.
REGLAS: list[tuple[str, list[str]]] = [
    (
        "asesor",
        [
            r"\basesor(a|es)?\b",
            r"\bhumano\b",
            r"\bpersona\b",
            r"alguien real",
            r"\bvendedor(a)?\b",
            r"\bencargad[oa]\b",
            r"\bllam(e|en|ar|arme|enme|ame)\b",
            r"comunicar(me)? con",
            r"hablar con (alguien|el due|la due)",
        ],
    ),
    (
        "estado_pedido",
        [
            r"\bpedido\b",
            r"\borden\b",
            r"\bencargo\b",
            r"cuando (estara|esta|va a estar|me entregan|entregan|llega)",
            r"ya esta (listo|lista)",
            r"como va (mi|el)",
            r"\bretirar\b",
        ],
    ),
    (
        "cotizar",
        [
            r"cotiz",
            r"\bprecio",
            r"\bcosto\b",
            r"\bvalor\b",
            r"\bpresupuesto\b",
            r"cuanto (cuesta|cuestan|vale|valen|sale|salen|saldria|seria|cobran)",
            r"configur",
        ],
    ),
    (
        "catalogo",
        [
            r"catalogo",
            r"\bmodelos?\b",
            r"\bdisenos?\b",
            r"\bfotos?\b",
            r"que (tienen|venden|ofrecen|manejan)",
            r"\b(tienen|venden|manejan)\b",
            r"\bver (sus |las |los )?(joyas|anillos|cadenas|pulseras|aretes|argollas|dijes|productos|opciones)\b",
            r"\bmuestr(a|ame|en)\b",
        ],
    ),
    (
        "despedida",
        [
            r"\bgracias\b",
            r"\badios\b",
            r"\bchao\b",
            r"hasta (luego|pronto)",
            r"eso es todo",
            r"nos vemos",
        ],
    ),
    (
        "saludo",
        [
            r"^(hola|holi|buenas|buenos dias|buenas tardes|buenas noches|buen dia|saludos|hey|que tal)\b",
        ],
    ),
]


def normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sin_tildes)).strip()


def clasificar_con_reglas(texto: str) -> str:
    limpio = normalizar(texto)
    for intencion, patrones in REGLAS:
        if any(re.search(p, limpio) for p in patrones):
            return intencion
    return "otro"


PROMPT_CLASIFICADOR = (
    "Eres el clasificador de mensajes de una joyería. Clasifica el mensaje del "
    "cliente en UNA de estas intenciones y responde solo con la etiqueta, sin "
    "explicaciones:\n"
    "- saludo: solo saluda.\n"
    "- cotizar: pide precio o cotización de una joya.\n"
    "- catalogo: quiere ver o conocer las joyas o modelos disponibles, o busca ideas de regalo.\n"
    "- estado_pedido: pregunta por un pedido u orden que ya hizo.\n"
    "- asesor: quiere hablar con una persona.\n"
    "- despedida: se despide o agradece.\n"
    "- otro: cualquier otra cosa (horarios, ubicación, pagos, temas ajenos)."
)


def _etiqueta_de(respuesta: str) -> str | None:
    limpio = normalizar(respuesta).replace(" ", "_")
    for intencion in INTENCIONES:
        if intencion == limpio:
            return intencion
    for intencion in INTENCIONES:
        if intencion in limpio:
            return intencion
    return None


def clasificar(texto: str, proveedor: ProveedorLLM | None = None) -> str:
    """Con modelo si hay proveedor; si falla o responde algo raro, usa las reglas."""
    if proveedor is not None:
        try:
            etiqueta = _etiqueta_de(proveedor.generar(PROMPT_CLASIFICADOR, texto))
        except ErrorLLM:
            etiqueta = None
        if etiqueta is not None:
            return etiqueta
    return clasificar_con_reglas(texto)
