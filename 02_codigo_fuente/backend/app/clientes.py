import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import CacheIdentidad
from app.models import Cliente


def registrar_cliente(
    session: Session, canal: str, id_canal: str, nombre_perfil: str | None = None
) -> tuple[Cliente, bool]:
    cliente = session.scalar(
        select(Cliente).where(Cliente.canal == canal, Cliente.id_canal == id_canal)
    )
    if cliente:
        if nombre_perfil and not cliente.nombre_perfil:
            cliente.nombre_perfil = nombre_perfil  # un cliente sin nombre lo recibe cuando llega
            session.commit()
        return cliente, False
    cliente = Cliente(canal=canal, id_canal=id_canal, nombre_perfil=nombre_perfil)
    session.add(cliente)
    session.commit()
    return cliente, True


def identificar_cliente(
    session: Session,
    cache: CacheIdentidad,
    canal: str,
    id_canal: str,
    nombre_perfil: str | None = None,
) -> tuple[int, bool]:
    """Devuelve (id del cliente, si fue creado). Primero mira la caché."""
    cliente_id = cache.obtener(canal, id_canal)
    if cliente_id is not None:
        return cliente_id, False
    cliente, creado = registrar_cliente(session, canal, id_canal, nombre_perfil)
    cache.guardar(canal, id_canal, cliente.id)
    return cliente.id, creado


_LETRAS = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,30}")


def primer_nombre(nombre_perfil: str | None) -> str | None:
    """El primer nombre del perfil, sin emojis ni adornos ("Pablo 🎸" -> "Pablo")."""
    encontrado = _LETRAS.search(nombre_perfil or "")
    return encontrado.group(0).capitalize() if encontrado else None


def nombre_para_saludar(cliente: Cliente) -> str | None:
    """Cómo llamar al cliente: el nombre que él pidió o, si no ha dicho, el de su perfil."""
    return cliente.nombre_preferido or primer_nombre(cliente.nombre_perfil)
