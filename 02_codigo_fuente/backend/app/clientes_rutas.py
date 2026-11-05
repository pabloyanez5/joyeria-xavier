from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Cliente
from app.ordenes import nombre_de

router = APIRouter(prefix="/clientes", tags=["clientes"])


class ClienteOut(BaseModel):
    id: int
    nombre: str
    canal: str


@router.get("", response_model=list[ClienteOut])
def listar_clientes(
    limite: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)
):
    """Clientes más recientes primero; el panel del asesor los usa para elegir a quién va la orden."""
    clientes = session.scalars(select(Cliente).order_by(Cliente.id.desc()).limit(limite)).all()
    return [ClienteOut(id=c.id, nombre=nombre_de(c), canal=c.canal) for c in clientes]
