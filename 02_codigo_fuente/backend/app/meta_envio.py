"""Envío de mensajes salientes por la API de Meta: WhatsApp, Messenger e Instagram."""
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from app.mensajes import (
    LARGO_BOTON,
    LARGO_CUERPO,
    LARGO_DESCRIPCION,
    LARGO_FILA,
    MAX_BOTONES,
    MAX_FILAS,
    Saliente,
    cortar,
)

logger = logging.getLogger("joyeria.meta")

VERSION_POR_DEFECTO = "v23.0"

# Canales que se envían por la página de Facebook (Messenger e Instagram) y su largo máximo.
CANALES_DE_PAGINA = {"messenger": 2000, "instagram": 1000}
# Respuestas rápidas de Messenger e Instagram: hasta 13 y 20 caracteres cada una.
MAX_RESPUESTAS_RAPIDAS = 13
LARGO_RESPUESTA_RAPIDA = 20


class ErrorMeta(Exception):
    """La API de Meta rechazó el mensaje o no se pudo contactar."""


class Enviador:
    """Interfaz: manda un texto, o un mensaje con formato, a un cliente por su canal."""

    def enviar(self, canal: str, destinatario: str, texto: str) -> bool:
        raise NotImplementedError

    def enviar_saliente(self, canal: str, destinatario: str, saliente: Saliente) -> bool:
        """Por defecto manda la versión solo texto; cada canal puede mejorarlo."""
        return self.enviar(canal, destinatario, saliente.plano())

    def nombre_de_perfil(self, canal: str, id_canal: str) -> str | None:
        """Nombre público del cliente en su canal, si se puede consultar; si no, None."""
        return None


class EnviadorMeta(Enviador):
    def __init__(
        self,
        token: str,
        phone_number_id: str,
        version: str = VERSION_POR_DEFECTO,
        timeout: float = 10,
        intentos: int = 3,
        espera: float = 0.7,
        page_id: str = "",
        page_token: str = "",
    ):
        self.page_id = page_id
        self.page_token = page_token
        self.intentos = max(1, intentos)
        self.espera = espera
        self.token = token
        self.phone_number_id = phone_number_id
        self.version = version
        self.timeout = timeout

    def _url(self) -> str:
        return f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"

    @staticmethod
    def _cuerpo(destinatario: str, s: Saliente) -> dict:
        base = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": destinatario,
        }
        if s.tipo == "tarjeta" and s.botones and s.imagen_url:
            return {
                **base,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {"type": "image", "image": {"link": s.imagen_url}},
                    "body": {"text": s.texto[:LARGO_CUERPO]},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": b.id, "title": cortar(b.titulo, LARGO_BOTON)},
                            }
                            for b in s.botones[:MAX_BOTONES]
                        ]
                    },
                },
            }
        if s.tipo == "botones" and s.botones:
            return {
                **base,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": s.texto[:LARGO_CUERPO]},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": b.id, "title": cortar(b.titulo, LARGO_BOTON)},
                            }
                            for b in s.botones[:MAX_BOTONES]
                        ]
                    },
                },
            }
        if s.tipo == "lista" and s.filas:
            return {
                **base,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": s.texto[:LARGO_CUERPO]},
                    "action": {
                        "button": cortar(s.etiqueta_lista, LARGO_BOTON),
                        "sections": [
                            {
                                "title": "Opciones",
                                "rows": [
                                    {
                                        "id": f.id,
                                        "title": cortar(f.titulo, LARGO_FILA),
                                        **(
                                            {"description": cortar(f.descripcion, LARGO_DESCRIPCION)}
                                            if f.descripcion
                                            else {}
                                        ),
                                    }
                                    for f in s.filas[:MAX_FILAS]
                                ],
                            }
                        ],
                    },
                },
            }
        if s.tipo == "imagen" and s.imagen_url:
            return {
                **base,
                "type": "image",
                "image": {"link": s.imagen_url, "caption": s.texto[:LARGO_CUERPO]},
            }
        return {**base, "type": "text", "text": {"preview_url": True, "body": s.texto}}

    def enviar(self, canal: str, destinatario: str, texto: str) -> bool:
        """Devuelve True si Meta aceptó el mensaje; False si el canal aún no se envía."""
        return self.enviar_saliente(canal, destinatario, Saliente("texto", texto))

    def enviar_saliente(self, canal: str, destinatario: str, saliente: Saliente) -> bool:
        if canal == "whatsapp":
            return self._publicar(self._url(), self.token, self._cuerpo(destinatario, saliente))
        if canal in CANALES_DE_PAGINA:
            if not (self.page_id and self.page_token):
                logger.info("Falta META_PAGE_ID o META_PAGE_ACCESS_TOKEN para enviar por %s", canal)
                return False
            url = f"https://graph.facebook.com/{self.version}/{self.page_id}/messages"
            aceptado = True
            for mensaje in self._mensajes_de_pagina(canal, saliente):
                cuerpo = {
                    "recipient": {"id": destinatario},
                    "message": mensaje,
                    "messaging_type": "RESPONSE",
                }
                aceptado = self._publicar(url, self.page_token, cuerpo) and aceptado
            return aceptado
        logger.info("El envío por %s todavía no está implementado", canal)
        return False

    @staticmethod
    def _mensajes_de_pagina(canal: str, s: Saliente) -> list[dict]:
        """Messenger e Instagram: la foto va como imagen (no como enlace) y los botones o las
        opciones de una lista como respuestas rápidas, que el cliente toca igual que en WhatsApp.
        """
        largo = CANALES_DE_PAGINA[canal]
        mensajes = []
        if s.tipo in ("imagen", "tarjeta") and s.imagen_url:
            mensajes.append({"attachment": {"type": "image", "payload": {"url": s.imagen_url}}})
        if s.tipo == "tarjeta":
            opciones = [(b.id, b.titulo) for b in s.botones]
            texto = s.texto
        elif s.tipo == "botones":
            opciones = [(b.id, b.titulo) for b in s.botones]
            texto = s.texto
        elif s.tipo == "lista":
            # La lista se escribe completa (con su descripción) y cada opción queda para tocar.
            opciones = [(f.id, f.titulo) for f in s.filas]
            texto = s.plano()
        else:
            opciones = []
            texto = s.texto if s.tipo == "imagen" and s.imagen_url else s.plano()
        if texto.strip():
            mensaje: dict = {"text": texto[:largo]}
            if opciones:
                mensaje["quick_replies"] = [
                    {"content_type": "text", "title": cortar(titulo, LARGO_RESPUESTA_RAPIDA), "payload": id_}
                    for id_, titulo in opciones[:MAX_RESPUESTAS_RAPIDAS]
                ]
            mensajes.append(mensaje)
        return mensajes

    def nombre_de_perfil(self, canal: str, id_canal: str) -> str | None:
        """Messenger e Instagram no mandan el nombre en el webhook: se consulta a Meta.

        Es opcional y no debe frenar la respuesta: con un solo intento y poca espera,
        cualquier falla (sin permiso, sin red) devuelve None.
        """
        if canal not in CANALES_DE_PAGINA or not self.page_token:
            return None
        url = f"https://graph.facebook.com/{self.version}/{urllib.parse.quote(id_canal)}?fields=name"
        peticion = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self.page_token}"}, method="GET"
        )
        try:
            with urllib.request.urlopen(peticion, timeout=min(self.timeout, 3)) as respuesta:
                nombre = json.loads(respuesta.read()).get("name")
        except Exception as e:
            logger.info("No se pudo consultar el nombre del perfil en %s: %s", canal, type(e).__name__)
            return None
        return nombre.strip()[:200] if isinstance(nombre, str) and nombre.strip() else None

    def _publicar(self, url: str, token: str, cuerpo: dict) -> bool:
        peticion = urllib.request.Request(
            url,
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for intento in range(1, self.intentos + 1):
            try:
                with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                    respuesta.read()
                return True
            except urllib.error.HTTPError as e:
                # Meta sí respondió (token vencido, parámetros inválidos): reintentar no ayuda.
                detalle = e.read(500).decode("utf-8", "replace")
                raise ErrorMeta(f"Meta respondió {e.code}: {detalle}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                # Corte de red o DNS intermitente: se reintenta con una pausa corta.
                if intento == self.intentos:
                    raise ErrorMeta(f"No se pudo contactar a Meta: {e}") from e
                logger.warning(
                    "Sin red hacia Meta (intento %d de %d): %s", intento, self.intentos, e
                )
                time.sleep(self.espera * intento)
        return False


def enviador_desde_entorno() -> Enviador | None:
    """EnviadorMeta si hay META_ACCESS_TOKEN y META_PHONE_NUMBER_ID; si no, None.

    Messenger e Instagram usan además META_PAGE_ID y META_PAGE_ACCESS_TOKEN (opcionales).
    """
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    phone_id = os.getenv("META_PHONE_NUMBER_ID", "").strip()
    if not token or not phone_id:
        return None
    version = os.getenv("META_API_VERSION", "").strip() or VERSION_POR_DEFECTO
    return EnviadorMeta(
        token,
        phone_id,
        version,
        page_id=os.getenv("META_PAGE_ID", "").strip(),
        page_token=os.getenv("META_PAGE_ACCESS_TOKEN", "").strip(),
    )
