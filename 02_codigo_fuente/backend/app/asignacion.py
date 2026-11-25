"""Reparto de las conversaciones escaladas entre los asesores (JOY-84, RF-01 y CU-6).

- Al escalar, la conversación va al asesor activo con menos conversaciones escaladas abiertas;
  si empatan, al que hace más tiempo no recibe una (así se turnan).
- Si la conversación ya tenía un asesor activo (volvió a escalar), se queda con él.
- Si no hay asesores activos, queda en la cola general (sin asesor).
- Un asesor puede tomar una conversación o reasignarla a otro, o devolverla a la cola general.
  Cada cambio queda registrado con quién lo hizo y cuándo.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AsignacionConversacion, Conversacion, Usuario

ROL_QUE_ATIENDE = "asesor"


def asesores_activos(session: Session) -> list[Usuario]:
    return list(
        session.scalars(
            select(Usuario)
            .where(Usuario.rol == ROL_QUE_ATIENDE, Usuario.activo.is_(True))
            .order_by(Usuario.id)
        )
    )


def carga_de(session: Session, asesor_id: int) -> int:
    """Conversaciones escaladas (esperan a una persona) que tiene a su cargo."""
    return session.scalar(
        select(func.count())
        .select_from(Conversacion)
        .where(Conversacion.asesor_id == asesor_id, Conversacion.estado == "escalada")
    ) or 0


def _ultima_asignacion(session: Session, asesor_id: int) -> float:
    """Cuándo recibió su última conversación (0 si nunca): desempata a favor del que espera más."""
    ultima = session.scalar(
        select(func.max(Conversacion.asignada_en)).where(Conversacion.asesor_id == asesor_id)
    )
    if ultima is None:
        return 0.0
    return (ultima if ultima.tzinfo else ultima.replace(tzinfo=timezone.utc)).timestamp()


def _activo(session: Session, usuario_id: int | None) -> bool:
    usuario = session.get(Usuario, usuario_id) if usuario_id else None
    return bool(usuario and usuario.activo and usuario.rol == ROL_QUE_ATIENDE)


def asignar(
    session: Session,
    conversacion: Conversacion,
    asesor_id: int | None,
    tipo: str,
    usuario_id: int | None = None,
) -> None:
    """Pone la conversación a cargo del asesor (o en la cola general) y lo registra."""
    conversacion.asesor_id = asesor_id
    conversacion.asignada_en = datetime.now(timezone.utc) if asesor_id else None
    session.add(
        AsignacionConversacion(
            conversacion_id=conversacion.id, asesor_id=asesor_id, usuario_id=usuario_id, tipo=tipo
        )
    )


def asignar_al_escalar(session: Session, conversacion: Conversacion) -> int | None:
    """Reparto automático. Devuelve el id del asesor elegido, o None si quedó en la cola."""
    if _activo(session, conversacion.asesor_id):
        return conversacion.asesor_id  # vuelve a escalar: la sigue atendiendo el mismo
    session.flush()  # para contar bien las que se escalaron en esta misma transacción
    candidatos = asesores_activos(session)
    if not candidatos:
        if conversacion.asesor_id is not None:
            asignar(session, conversacion, None, "automatica")
        return None
    elegido = min(
        candidatos,
        key=lambda a: (carga_de(session, a.id), _ultima_asignacion(session, a.id), a.id),
    )
    asignar(session, conversacion, elegido.id, "automatica")
    return elegido.id
