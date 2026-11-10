"""Indicadores del negocio para el panel (RF-06).

Responde tres preguntas: ¿cuánto atiende el agente?, ¿cuánto resuelve solo frente a lo que
escala a una persona? y ¿cómo va la producción por etapa? Todo se calcula en el momento a partir
de las conversaciones, mensajes y órdenes reales; no hay cifras guardadas aparte.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    Cliente,
    Conversacion,
    HistorialEtapa,
    Mensaje,
    Orden,
    TransicionConversacion,
)
from app.ordenes import ETAPAS

router = APIRouter(prefix="/metricas", tags=["metricas"])


class DiaConversaciones(BaseModel):
    dia: str
    conversaciones: int


class EtapaConteo(BaseModel):
    etapa: str
    ordenes: int


class Metricas(BaseModel):
    dias: int
    clientes: int
    conversaciones: int
    por_estado: dict[str, int]
    escaladas: int  # conversaciones que en algún momento pasaron a una persona
    resueltas_por_agente: int  # las demás: el agente las atendió sin escalar
    tasa_resolucion_agente: float | None  # 0..100; None si aún no hay conversaciones
    mensajes: dict[str, int]  # cliente / agente / asesor / sistema
    ordenes_total: int
    ordenes_por_etapa: list[EtapaConteo]
    ordenes_con_acuse_pendiente: int
    horas_promedio_entrega: float | None
    conversaciones_por_dia: list[DiaConversaciones]


def _como_utc(valor: datetime) -> datetime:
    return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)


@router.get("", response_model=Metricas)
def metricas(
    dias: int = Query(30, ge=1, le=365), session: Session = Depends(get_session)
) -> Metricas:
    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(days=dias)

    conversaciones = session.scalars(
        select(Conversacion).where(Conversacion.creado_en >= desde)
    ).all()
    ids = [c.id for c in conversaciones]

    por_estado = {estado: 0 for estado in ("activa", "escalada", "cerrada")}
    for c in conversaciones:
        por_estado[c.estado] = por_estado.get(c.estado, 0) + 1

    escaladas = 0
    if ids:
        escaladas = session.scalar(
            select(func.count(func.distinct(TransicionConversacion.conversacion_id))).where(
                TransicionConversacion.conversacion_id.in_(ids),
                TransicionConversacion.estado_nuevo == "escalada",
            )
        )
    total = len(conversaciones)
    resueltas = total - escaladas
    tasa = round(resueltas * 100 / total, 1) if total else None

    mensajes = {"cliente": 0, "agente": 0, "asesor": 0, "sistema": 0}
    if ids:
        filas = session.execute(
            select(Mensaje.direccion, Mensaje.autor, func.count())
            .where(Mensaje.conversacion_id.in_(ids))
            .group_by(Mensaje.direccion, Mensaje.autor)
        ).all()
        for direccion, autor, cuantos in filas:
            clave = "cliente" if direccion == "entrante" else (autor or "agente")
            mensajes[clave] = mensajes.get(clave, 0) + cuantos

    conteo = dict(
        session.execute(select(Orden.etapa_actual, func.count()).group_by(Orden.etapa_actual)).all()
    )
    ordenes_por_etapa = [EtapaConteo(etapa=e, ordenes=conteo.get(e, 0)) for e in ETAPAS]
    pendientes = session.scalar(
        select(func.count()).select_from(Orden).where(Orden.acuse_pendiente.is_(True))
    )

    entregas = session.execute(
        select(Orden.creado_en, HistorialEtapa.creado_en)
        .join(HistorialEtapa, HistorialEtapa.orden_id == Orden.id)
        .where(HistorialEtapa.etapa == "entregada")
    ).all()
    horas = [
        (_como_utc(fin) - _como_utc(inicio)).total_seconds() / 3600
        for inicio, fin in entregas
        if inicio and fin
    ]

    por_dia = {(ahora - timedelta(days=i)).date().isoformat(): 0 for i in range(6, -1, -1)}
    for c in conversaciones:
        dia = _como_utc(c.creado_en).date().isoformat()
        if dia in por_dia:
            por_dia[dia] += 1

    return Metricas(
        dias=dias,
        clientes=session.scalar(select(func.count()).select_from(Cliente)),
        conversaciones=total,
        por_estado=por_estado,
        escaladas=escaladas,
        resueltas_por_agente=resueltas,
        tasa_resolucion_agente=tasa,
        mensajes=mensajes,
        ordenes_total=sum(conteo.values()),
        ordenes_por_etapa=ordenes_por_etapa,
        ordenes_con_acuse_pendiente=pendientes,
        horas_promedio_entrega=round(sum(horas) / len(horas), 1) if horas else None,
        conversaciones_por_dia=[
            DiaConversaciones(dia=d, conversaciones=n) for d, n in por_dia.items()
        ],
    )
