"""Consulta de los intentos que bloqueó la seguridad del agente (JOY-74, RNF-01).

Es de dirección (y admin): muestra cuándo, por qué canal, qué regla saltó y en qué
conversación quedó el mensaje, sin repetir lo que escribió el cliente.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.acceso import requiere
from app.agente.proteccion import MOTIVOS
from app.db import get_session
from app.models import Cliente, IntentoBloqueado, Mensaje

router = APIRouter(
    prefix="/seguridad", tags=["seguridad"], dependencies=[Depends(requiere("direccion"))]
)


class IntentoOut(BaseModel):
    id: int
    creado_en: datetime
    canal: str
    motivo: str
    regla: str | None
    cliente: str | None
    conversacion_id: int | None


class IntentosOut(BaseModel):
    dias: int
    total: int
    por_motivo: dict[str, int]
    intentos: list[IntentoOut]


def conteo_por_motivo(session: Session, desde: datetime) -> dict[str, int]:
    filas = dict(
        session.execute(
            select(IntentoBloqueado.motivo, func.count())
            .where(IntentoBloqueado.creado_en >= desde)
            .group_by(IntentoBloqueado.motivo)
        ).all()
    )
    return {motivo: filas.get(motivo, 0) for motivo in MOTIVOS}


@router.get("/intentos", response_model=IntentosOut)
def intentos_bloqueados(
    dias: int = Query(30, ge=1, le=365),
    motivo: str | None = Query(None, description="instrucciones, limite_de_mensajes o respuesta_corregida"),
    limite: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> IntentosOut:
    if motivo is not None and motivo not in MOTIVOS:
        raise HTTPException(422, "El motivo debe ser " + ", ".join(MOTIVOS))
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    consulta = (
        select(IntentoBloqueado, Cliente, Mensaje.conversacion_id)
        .outerjoin(Cliente, Cliente.id == IntentoBloqueado.cliente_id)
        .outerjoin(Mensaje, Mensaje.id == IntentoBloqueado.mensaje_id)
        .where(IntentoBloqueado.creado_en >= desde)
    )
    if motivo:
        consulta = consulta.where(IntentoBloqueado.motivo == motivo)
    filas = session.execute(
        consulta.order_by(IntentoBloqueado.creado_en.desc(), IntentoBloqueado.id.desc()).limit(limite)
    ).all()
    por_motivo = conteo_por_motivo(session, desde)
    return IntentosOut(
        dias=dias,
        total=sum(por_motivo.values()),
        por_motivo=por_motivo,
        intentos=[
            IntentoOut(
                id=i.id,
                creado_en=i.creado_en,
                canal=i.canal,
                motivo=i.motivo,
                regla=i.regla,
                cliente=(c.nombre_preferido or c.nombre_perfil) if c else None,
                conversacion_id=conversacion_id,
            )
            for i, c, conversacion_id in filas
        ],
    )
