"""Guardrails del agente conversacional (RNF-01 Seguridad y RNF-09 Protección).

Dos barreras que se suman a las instrucciones del modelo:

- Entrada: un mensaje que intenta cambiar las instrucciones del agente, sacarle su
  configuración o saltarse sus reglas no llega al modelo; se responde con un mensaje fijo.
- Salida: si la respuesta del modelo deja salir sus instrucciones, o trae teléfonos o correos
  que ninguna herramienta entregó, se corrige antes de enviarla al cliente.
"""
import re
import unicodedata

RESPUESTA_SEGURA = (
    "Solo puedo ayudarte con joyas, cotizaciones y el estado de tus pedidos de Joyería Xavier. "
    "¿Seguimos con lo que estabas buscando?"
)

# Frases del prompt que nunca deben aparecer en una respuesta al cliente.
MARCAS_DE_INSTRUCCIONES = (
    "cómo debes responder",
    "reglas de seguridad",
    "herramienta de preferencias",
    "aviso interno",
)

# Se aplican sobre el texto en minúsculas y sin tildes.
_PATRONES_DE_ATAQUE = [
    re.compile(p)
    for p in (
        r"\b(ignora|ignore|olvida|olvidate|omite|desobedece|salta|saltate)\b.{0,40}"
        r"\b(instrucciones|reglas|indicaciones|prompt|restricciones|lo anterior)\b",
        r"\b(ignore|disregard|forget)\b.{0,40}\b(instructions|rules|prompt|previous)\b",
        r"\b(system prompt|prompt del sistema|prompt inicial)\b",
        r"\binstrucciones (internas|ocultas|del sistema|iniciales|originales)\b",
        r"\b(muestra|muestrame|dime|revela|repite|imprime|escribe|cual es)\b.{0,30}"
        r"\b(tus|tu|las)\b.{0,15}\b(instrucciones|prompt|reglas internas)\b",
        r"\b(modo (desarrollador|dios|administrador|admin|sin restricciones)|developer mode|"
        r"jailbreak|dan mode)\b",
        r"\bactua como\b.{0,40}\b(sin (restricciones|reglas|filtros)|administrador|desarrollador)\b",
        r"\b(a partir de ahora|desde ahora)\b.{0,30}\b(eres|seras|ya no eres)\b",
    )
]

_TELEFONO = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MIN_DIGITOS_TELEFONO = 9  # un celular de Ecuador tiene 10; así no se confunden fechas o precios


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def es_intento_de_ataque(texto: str) -> bool:
    """True si el mensaje trata de cambiar o sacar las instrucciones del agente."""
    limpio = _normalizar(texto)
    return any(p.search(limpio) for p in _PATRONES_DE_ATAQUE)


def proteger_salida(respuesta: str, texto_de_herramientas: str = "") -> str:
    """Corrige la respuesta del modelo antes de enviarla al cliente.

    Los teléfonos y correos solo se dejan pasar si los entregó una herramienta
    (por ejemplo, los canales de contacto de la joyería).
    """
    minuscula = respuesta.lower()
    if any(marca in minuscula for marca in MARCAS_DE_INSTRUCCIONES):
        return RESPUESTA_SEGURA

    telefonos_validos = {
        _digitos(m.group(0)) for m in _TELEFONO.finditer(texto_de_herramientas)
    }
    correos_validos = {m.group(0).lower() for m in _CORREO.finditer(texto_de_herramientas)}

    def telefono(m: re.Match) -> str:
        digitos = _digitos(m.group(0))
        if len(digitos) < _MIN_DIGITOS_TELEFONO or digitos in telefonos_validos:
            return m.group(0)
        return "(dato omitido)"

    def correo(m: re.Match) -> str:
        return m.group(0) if m.group(0).lower() in correos_validos else "(dato omitido)"

    return _TELEFONO.sub(telefono, _CORREO.sub(correo, respuesta))
