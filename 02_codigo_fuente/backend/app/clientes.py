from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cliente


def registrar_cliente(
    session: Session, canal: str, id_canal: str, nombre_perfil: str | None = None
) -> tuple[Cliente, bool]:
    cliente = session.scalar(
        select(Cliente).where(Cliente.canal == canal, Cliente.id_canal == id_canal)
    )
    if cliente:
        return cliente, False
    cliente = Cliente(canal=canal, id_canal=id_canal, nombre_perfil=nombre_perfil)
    session.add(cliente)
    session.commit()
    return cliente, True