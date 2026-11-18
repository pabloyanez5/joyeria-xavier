import os
from urllib.parse import quote

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/contacto", tags=["contacto"])


class CanalOut(BaseModel):
    canal: str
    nombre: str
    enlace: str


def armar_canales(mensaje: str) -> list[CanalOut]:
    """Solo los canales configurados: un enlace sin número de WhatsApp no llega a nadie."""
    canales = []
    numero = os.getenv("JOYERIA_WHATSAPP", "").strip().lstrip("+").replace(" ", "")
    if numero:
        canales.append(
            CanalOut(
                canal="whatsapp",
                nombre="WhatsApp",
                enlace=f"https://wa.me/{numero}?text={quote(mensaje)}",
            )
        )
    instagram = os.getenv("JOYERIA_INSTAGRAM", "").strip()
    if instagram:
        canales.append(
            CanalOut(
                canal="instagram",
                nombre="Instagram",
                enlace=f"https://ig.me/m/{instagram}",
            )
        )
    messenger = os.getenv("JOYERIA_MESSENGER", "").strip()
    if messenger:
        canales.append(
            CanalOut(
                canal="messenger",
                nombre="Messenger",
                enlace=f"https://m.me/{messenger}",
            )
        )
    return canales


@router.get("", response_model=list[CanalOut])
def canales_de_contacto(
    mensaje: str = Query("Hola, quiero hablar con un asesor.", max_length=300),
):
    return armar_canales(mensaje)