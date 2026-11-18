"""Seguridad del agente II (JOY-74, RNF-01): límite de mensajes por cliente y registro de lo
que la seguridad bloquea.

- Límite: cada cliente puede mandar hasta AGENTE_LIMITE_MENSAJES mensajes cada
  AGENTE_LIMITE_SEGUNDOS. El que se pasa recibe un aviso (una sola vez por ventana) y el
  modelo no se llama; sus mensajes igual quedan en la conversación para el asesor.
- Registro: cada bloqueo queda en la tabla intentos_bloqueados con fecha, cliente, canal,
  motivo y regla, sin copiar lo que escribió el cliente.
"""
import logging
import os
from dataclasses import dataclass

import redis
from sqlalchemy.orm import Session

from app.models import IntentoBloqueado

logger = logging.getLogger("joyeria.seguridad")

LIMITE_POR_DEFECTO = 15
SEGUNDOS_POR_DEFECTO = 60

AVISO_LIMITE = (
    "Recibí muchos mensajes seguidos y necesito un momento para ponerme al día. "
    "Escríbeme de nuevo en un minuto, por favor."
)

MOTIVOS = ("instrucciones", "limite_de_mensajes", "respuesta_corregida")


def _entero(variable: str, por_defecto: int) -> int:
    try:
        valor = int(os.getenv(variable, "").strip() or por_defecto)
    except ValueError:
        return por_defecto
    return valor if valor > 0 else por_defecto


def limite_configurado() -> tuple[int, int]:
    """(mensajes, segundos) del límite por cliente."""
    return (
        _entero("AGENTE_LIMITE_MENSAJES", LIMITE_POR_DEFECTO),
        _entero("AGENTE_LIMITE_SEGUNDOS", SEGUNDOS_POR_DEFECTO),
    )


@dataclass
class Revision:
    permitido: bool
    avisar: bool = False  # True solo con el primer mensaje que se pasa del límite
    cuenta: int = 0


class LimiteDeMensajes:
    """Cuenta los mensajes de cada cliente en Redis. Si Redis falla, no bloquea a nadie."""

    def __init__(self, cliente_redis, maximo: int | None = None, segundos: int | None = None):
        configurado = limite_configurado()
        self.redis = cliente_redis
        self.maximo = maximo or configurado[0]
        self.segundos = segundos or configurado[1]

    @staticmethod
    def _clave(canal: str, id_canal: str) -> str:
        return f"limite:{canal}:{id_canal}"

    def revisar(self, canal: str, id_canal: str) -> Revision:
        clave = self._clave(canal, id_canal)
        try:
            cuenta = int(self.redis.incr(clave))
            if cuenta == 1:
                self.redis.expire(clave, self.segundos)
        except redis.RedisError:
            logger.warning("Sin Redis para el límite de mensajes: se deja pasar")
            return Revision(True)
        if cuenta <= self.maximo:
            return Revision(True, cuenta=cuenta)
        return Revision(False, avisar=cuenta == self.maximo + 1, cuenta=cuenta)


def registrar(
    session: Session,
    canal: str,
    motivo: str,
    cliente_id: int | None = None,
    mensaje_id: int | None = None,
    regla: str | None = None,
) -> IntentoBloqueado:
    """Anota el bloqueo (se guarda con el resto de la transacción)."""
    intento = IntentoBloqueado(
        canal=canal, motivo=motivo, cliente_id=cliente_id, mensaje_id=mensaje_id, regla=regla
    )
    session.add(intento)
    logger.warning(
        "Intento bloqueado: %s%s (cliente %s, %s)",
        motivo,
        f"/{regla}" if regla else "",
        cliente_id,
        canal,
    )
    return intento
