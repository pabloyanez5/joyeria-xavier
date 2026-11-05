import logging
import os
from dataclasses import dataclass

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.agente.llm import ProveedorLLM
from app.agente.rutas import get_proveedor
from app.agente.servicio import atender_mensaje
from app.cache import CacheIdentidad, get_cache
from app.clientes import identificar_cliente
from app.db import get_session

logger = logging.getLogger("joyeria.webhook")

router = APIRouter(prefix="/webhook", tags=["webhook"])

CANALES = {
    "whatsapp_business_account": "whatsapp",
    "instagram": "instagram",
    "page": "messenger",
}


def get_verify_token() -> str:
    return os.getenv("META_VERIFY_TOKEN", "cambia-esto")


def extraer_remitentes(payload: dict) -> list[tuple[str, str, str | None]]:
    """Devuelve (canal, id_canal, nombre) de cada mensaje entrante."""
    canal = CANALES.get(payload.get("object"))
    if canal is None:
        return []
    remitentes = []
    for entry in payload.get("entry", []):
        if canal == "whatsapp":
            for change in entry.get("changes", []):
                value = change.get("value", {})
                nombres = {
                    c.get("wa_id"): c.get("profile", {}).get("name")
                    for c in value.get("contacts", [])
                }
                for msg in value.get("messages", []):
                    id_canal = msg.get("from")
                    if id_canal:
                        remitentes.append((canal, id_canal, nombres.get(id_canal)))
        else:
            for evento in entry.get("messaging", []):
                mensaje = evento.get("message")
                id_canal = evento.get("sender", {}).get("id")
                if id_canal and mensaje and not mensaje.get("is_echo"):
                    remitentes.append((canal, id_canal, None))
    return remitentes


@dataclass
class Entrante:
    canal: str
    id_canal: str
    nombre: str | None
    texto: str | None  # None si no es un mensaje de texto (imagen, audio, etc.)
    id_externo: str | None


def extraer_mensajes(payload: dict) -> list[Entrante]:
    """Devuelve cada mensaje entrante con su texto (si lo tiene) y su id en Meta."""
    canal = CANALES.get(payload.get("object"))
    if canal is None:
        return []
    mensajes = []
    for entry in payload.get("entry", []):
        if canal == "whatsapp":
            for change in entry.get("changes", []):
                value = change.get("value", {})
                nombres = {
                    c.get("wa_id"): c.get("profile", {}).get("name")
                    for c in value.get("contacts", [])
                }
                for msg in value.get("messages", []):
                    id_canal = msg.get("from")
                    if not id_canal:
                        continue
                    texto = None
                    if msg.get("type") == "text":
                        texto = (msg.get("text") or {}).get("body")
                    mensajes.append(
                        Entrante(canal, id_canal, nombres.get(id_canal), texto, msg.get("id"))
                    )
        else:
            for evento in entry.get("messaging", []):
                mensaje = evento.get("message")
                id_canal = evento.get("sender", {}).get("id")
                if id_canal and mensaje and not mensaje.get("is_echo"):
                    mensajes.append(
                        Entrante(canal, id_canal, None, mensaje.get("text"), mensaje.get("mid"))
                    )
    return mensajes


def _ocultar(id_canal: str) -> str:
    """Para los registros (logs): no se escribe el número completo del cliente."""
    return f"***{id_canal[-4:]}"


@router.get("/meta", response_class=PlainTextResponse)
def verificar_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == get_verify_token():
        return hub_challenge or ""
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@router.post("/meta")
def recibir_mensaje(
    payload: dict = Body(...),
    session: Session = Depends(get_session),
    cache: CacheIdentidad = Depends(get_cache),
    proveedor: ProveedorLLM | None = Depends(get_proveedor),
):
    """Recibe los mensajes de Meta y deja que el agente los atienda.

    Por ahora las respuestas se guardan y se escriben en el registro, pero no se
    envían a Meta (falta la cuenta verificada). Siempre se responde 200 para que
    Meta no reintente el envío si algo falla con un mensaje.
    """
    nuevos = 0
    respuestas = 0
    for m in extraer_mensajes(payload):
        try:
            if m.texto:
                resultado = atender_mensaje(
                    session,
                    cache,
                    m.canal,
                    m.id_canal,
                    m.texto,
                    nombre=m.nombre,
                    id_externo=m.id_externo,
                    proveedor=proveedor,
                )
                nuevos += resultado.cliente_nuevo
                if resultado.texto:
                    respuestas += 1
                    logger.info(
                        "Respuesta del agente a %s %s (%s): %s",
                        m.canal,
                        _ocultar(m.id_canal),
                        resultado.intencion,
                        resultado.texto,
                    )
            else:
                _, creado = identificar_cliente(session, cache, m.canal, m.id_canal, m.nombre)
                nuevos += creado
        except Exception:
            session.rollback()
            logger.exception("No se pudo atender un mensaje de %s", m.canal)
    return {"status": "ok", "clientes_nuevos": nuevos, "respuestas": respuestas}
