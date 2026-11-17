from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.acceso import requiere
from app.db import get_session
from app.models import Cliente
from app.ordenes import nombre_de

# Los datos de los clientes son solo para el asesor (RNF-09).
router = APIRouter(
    prefix="/clientes", tags=["clientes"], dependencies=[Depends(requiere("asesor"))]
)


class ClienteOut(BaseModel):
    id: int
    nombre: str
    canal: str
    # Para precargar el formulario de la orden; el asesor los confirma con el cliente.
    nombre_completo: str | None = None
    telefono: str | None = None


def _telefono_sugerido(cliente: Cliente) -> str | None:
    """El teléfono confirmado o, en WhatsApp, el número desde el que escribe."""
    if cliente.telefono:
        return cliente.telefono
    return cliente.id_canal if cliente.canal == "whatsapp" and cliente.id_canal.isdigit() else None


@router.get("", response_model=list[ClienteOut])
def listar_clientes(
    limite: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)
):
    """Clientes más recientes primero; el panel del asesor los usa para elegir a quién va la orden."""
    clientes = session.scalars(select(Cliente).order_by(Cliente.id.desc()).limit(limite)).all()
    return [
        ClienteOut(
            id=c.id,
            nombre=nombre_de(c),
            canal=c.canal,
            nombre_completo=c.nombre_completo,
            telefono=_telefono_sugerido(c),
        )
        for c in clientes
    ]
