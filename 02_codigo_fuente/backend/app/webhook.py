import os

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.clientes import registrar_cliente
from app.db import get_session

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
    payload: dict = Body(...), session: Session = Depends(get_session)
):
    nuevos = 0
    for canal, id_canal, nombre in extraer_remitentes(payload):
        _, creado = registrar_cliente(session, canal, id_canal, nombre)
        nuevos += creado
    return {"status": "ok", "clientes_nuevos": nuevos}