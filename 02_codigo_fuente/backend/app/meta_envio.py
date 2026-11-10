"""Envío de mensajes salientes por la API de Meta (por ahora solo WhatsApp)."""
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("joyeria.meta")

VERSION_POR_DEFECTO = "v23.0"


class ErrorMeta(Exception):
    """La API de Meta rechazó el mensaje o no se pudo contactar."""


class Enviador:
    """Interfaz: manda un texto a un cliente por su canal."""

    def enviar(self, canal: str, destinatario: str, texto: str) -> bool:
        raise NotImplementedError


class EnviadorMeta(Enviador):
    def __init__(
        self,
        token: str,
        phone_number_id: str,
        version: str = VERSION_POR_DEFECTO,
        timeout: float = 10,
    ):
        self.token = token
        self.phone_number_id = phone_number_id
        self.version = version
        self.timeout = timeout

    def _url(self) -> str:
        return f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"

    def enviar(self, canal: str, destinatario: str, texto: str) -> bool:
        """Devuelve True si Meta aceptó el mensaje; False si el canal aún no se envía."""
        if canal != "whatsapp":
            logger.info("El envío por %s todavía no está implementado", canal)
            return False
        cuerpo = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": destinatario,
            "type": "text",
            "text": {"preview_url": True, "body": texto},
        }
        peticion = urllib.request.Request(
            self._url(),
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                respuesta.read()
        except urllib.error.HTTPError as e:
            detalle = e.read(500).decode("utf-8", "replace")
            raise ErrorMeta(f"Meta respondió {e.code}: {detalle}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise ErrorMeta(f"No se pudo contactar a Meta: {e}") from e
        return True


def enviador_desde_entorno() -> Enviador | None:
    """EnviadorMeta si hay META_ACCESS_TOKEN y META_PHONE_NUMBER_ID; si no, None."""
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    phone_id = os.getenv("META_PHONE_NUMBER_ID", "").strip()
    if not token or not phone_id:
        return None
    version = os.getenv("META_API_VERSION", "").strip() or VERSION_POR_DEFECTO
    return EnviadorMeta(token, phone_id, version)
