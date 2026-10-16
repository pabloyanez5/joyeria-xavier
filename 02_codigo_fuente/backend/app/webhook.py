import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/webhook", tags=["webhook"])


def get_verify_token() -> str:
    return os.getenv("META_VERIFY_TOKEN", "cambia-esto")


@router.get("/meta", response_class=PlainTextResponse)
def verificar_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == get_verify_token():
        return hub_challenge or ""
    raise HTTPException(status_code=403, detail="Token de verificación inválido")