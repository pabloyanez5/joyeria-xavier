"""Escalamiento automático a un asesor (JOY-85, RF-01 y RNF-02).

El agente pasa la conversación a una persona, sin que el cliente lo pida, cuando:

- el cliente está molesto;
- pide algo que el agente no puede resolver con sus herramientas (reparaciones, ajustes de
  talla, grabados, diseños a medida, devoluciones, garantías, facturas o citas);
- pide una cotización fuera de lo que el sistema calcula (otro material o quilataje, o un
  presupuesto por encima del máximo configurado);
- no logra entender dos mensajes seguidos.

Las tres primeras se revisan antes de llamar al modelo (son reglas, siempre igual); la cuarta la
lleva el motor de reglas con un contador, y el modelo tiene la misma indicación en sus
instrucciones. El motivo queda en la ficha para el asesor.
"""
import os
import re
from dataclasses import dataclass

from app.agente.contexto import ocasion_y_presupuesto
from app.agente.intenciones import normalizar

MAXIMO_POR_DEFECTO = 5000


@dataclass(frozen=True)
class Escalamiento:
    tipo: str  # molesto | sin_herramienta | fuera_de_rango | no_entendido | pedido | sin_orden
    motivo: str  # lo que ve el asesor en la ficha
    respuesta: str  # lo que recibe el cliente


RESPUESTAS = {
    "molesto": (
        "Lamento mucho la molestia. Te comunico ahora mismo con un asesor para que lo resuelva "
        "contigo; en breve te atenderá una persona."
    ),
    "sin_herramienta": (
        "Eso lo coordina directamente un asesor de la joyería. Te comunico con uno; en breve te "
        "atenderá una persona."
    ),
    "fuera_de_rango": (
        "Esa cotización la prepara un asesor, porque está fuera de lo que puedo calcular por aquí. "
        "Te comunico con uno; en breve te atenderá una persona."
    ),
    "no_entendido": (
        "Disculpa, no logro entenderte. Te comunico con un asesor para que te ayude; en breve te "
        "atenderá una persona."
    ),
}

# Se aplican sobre el texto normalizado (minúsculas, sin tildes ni signos).
_MOLESTO = [
    re.compile(p)
    for p in (
        r"\b(pesimo|pesima|horrible|terrible|una verguenza|un asco|fatal)\b",
        r"\b(estafa|estafadores|ladrones|robo|me robaron|me enganaron|enganan)\b",
        r"\b(harto|harta|cansado de|cansada de|indignado|indignada|furioso|furiosa|enojado|"
        r"enojada|decepcionado|decepcionada)\b",
        # «estoy molesto» sí; «¿le molesta si…?» o «disculpe la molestia», no.
        r"\b(estoy|me tienen|ya estoy|sigo) (muy )?(molesto|molesta|enojado|enojada)\b",
        r"\b(mal servicio|pesimo servicio|nadie (me )?(responde|contesta|atiende)|ya les dije|"
        r"cuantas veces|siempre lo mismo|no es posible que)\b",
        r"\b(voy a (denunciar|poner una queja|reclamar)|quiero (poner )?(una )?queja|reclamo formal|"
        r"defensoria del consumidor)\b",
    )
]

_SIN_HERRAMIENTA = {
    "reparación": r"\b(reparacion|reparaciones|reparar|arreglo|arreglar|soldar|se (me )?rompio)\b",
    "ajuste de talla": r"\b(ajustar|agrandar|achicar|cambiar|cambio de) (la |el )?talla\b",
    "grabado": r"\b(grabado|grabar|grabarle|gravado|gravar)\b",
    "diseño a medida": r"\b(diseno (personalizado|propio|exclusivo|unico)|a medida|mi propio diseno|"
    r"hacer un diseno|tengo un diseno)\b",
    "devolución o garantía": r"\b(devolucion|devolver|reembolso|garantia|cambiar la joya|"
    r"cambio de (la )?joya)\b",
    "factura": r"\b(factura|facturar|ruc para la factura)\b",
    "cita en la joyería": r"\b(cita|agendar|agendame|separar una hora|visita a la joyeria)\b",
}

# Lo que el catálogo cotiza: oro 14k y 18k, y plata.
_FUERA_DE_CATALOGO = {
    "otro quilataje": r"\b(9|10|12|20|21|22|24) ?(k|kt|quilates)\b",
    "otro material": r"\b(platino|oro blanco|oro rosa|oro rosado|titanio|acero|paladio|plata 950)\b",
}


def maximo_cotizable() -> int:
    """AGENTE_COTIZACION_MAXIMA: un presupuesto mayor lo atiende un asesor (por defecto 5000)."""
    try:
        valor = int(os.getenv("AGENTE_COTIZACION_MAXIMA", "").strip() or MAXIMO_POR_DEFECTO)
    except ValueError:
        return MAXIMO_POR_DEFECTO
    return valor if valor > 0 else MAXIMO_POR_DEFECTO


def _escalar(tipo: str, motivo: str) -> Escalamiento:
    return Escalamiento(tipo, motivo, RESPUESTAS[tipo])


def antes_del_modelo(texto: str) -> Escalamiento | None:
    """Molestia, pedido sin herramienta o cotización fuera de rango: se escala sin llamar al modelo."""
    limpio = normalizar(texto)
    if any(p.search(limpio) for p in _MOLESTO):
        return _escalar("molesto", "El cliente está molesto")
    for que, patron in _SIN_HERRAMIENTA.items():
        if re.search(patron, limpio):
            return _escalar("sin_herramienta", f"Pide algo que el agente no puede resolver: {que}")
    for que, patron in _FUERA_DE_CATALOGO.items():
        encontrado = re.search(patron, limpio)
        if encontrado:
            return _escalar(
                "fuera_de_rango", f"Cotización fuera de lo que calcula el sistema: {que} ({encontrado.group(0)})"
            )
    presupuesto = ocasion_y_presupuesto(texto).get("presupuesto")
    if presupuesto and int(presupuesto.lstrip("$")) > maximo_cotizable():
        return _escalar(
            "fuera_de_rango",
            f"Cotización fuera de lo que calcula el sistema: presupuesto de {presupuesto}",
        )
    return None


def no_entendido(contexto: dict) -> tuple[dict, Escalamiento | None]:
    """Suma un mensaje no entendido; al segundo seguido, escala."""
    contexto = {**contexto, "no_entendidos": int(contexto.get("no_entendidos", 0)) + 1}
    if contexto["no_entendidos"] >= 2:
        contexto["no_entendidos"] = 0
        return contexto, _escalar("no_entendido", "El agente no entendió dos mensajes seguidos")
    return contexto, None


def entendido(contexto: dict) -> dict:
    """Un mensaje entendido reinicia la cuenta."""
    if not contexto.get("no_entendidos"):
        return contexto
    return {k: v for k, v in contexto.items() if k != "no_entendidos"}
