from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agente.llm import ProveedorLLM, proveedor_desde_entorno
from app.agente.servicio import atender_mensaje
from app.cache import CacheIdentidad, get_cache
from app.db import get_session

router = APIRouter(prefix="/agente", tags=["agente"])


class MensajeIn(BaseModel):
    canal: Literal["whatsapp", "instagram", "messenger"]
    id_canal: str = Field(min_length=1, max_length=100)
    texto: str = Field(min_length=1, max_length=1000)
    nombre: str | None = Field(None, max_length=200)
    id_externo: str | None = Field(None, max_length=200)


class RespuestaOut(BaseModel):
    respuesta: str | None
    intencion: str | None
    conversacion_id: int
    escalada: bool
    duplicado: bool


@lru_cache
def get_proveedor() -> ProveedorLLM | None:
    return proveedor_desde_entorno()


@lru_cache
def get_modelo_chat():
    """Modelo de chat de LangChain (Gemini) o None si no hay clave o falta la librería."""
    try:
        from app.agente.lc_agente import crear_modelo_desde_entorno

        return crear_modelo_desde_entorno()
    except ImportError:
        return None


@router.post("/mensajes", response_model=RespuestaOut)
def enviar_mensaje(
    datos: MensajeIn,
    session: Session = Depends(get_session),
    cache: CacheIdentidad = Depends(get_cache),
    proveedor: ProveedorLLM | None = Depends(get_proveedor),
    modelo=Depends(get_modelo_chat),
):
    """Simula un mensaje entrante de un cliente (sirve para la demo y las pruebas)."""
    resultado = atender_mensaje(
        session,
        cache,
        datos.canal,
        datos.id_canal,
        datos.texto,
        nombre=datos.nombre,
        id_externo=datos.id_externo,
        proveedor=proveedor,
        modelo=modelo,
    )
    return RespuestaOut(
        respuesta=resultado.texto,
        intencion=resultado.intencion,
        conversacion_id=resultado.conversacion_id,
        escalada=resultado.escalada,
        duplicado=resultado.duplicado,
    )
