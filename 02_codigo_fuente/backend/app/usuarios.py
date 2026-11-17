"""Administración de los usuarios del panel desde la línea de comandos (JOY-78).

    python -m app.usuarios crear --nombre "Ana Ruiz" --email ana@joyeria.test --rol asesor
    python -m app.usuarios clave --email ana@joyeria.test
    python -m app.usuarios desactivar --email ana@joyeria.test
    python -m app.usuarios listar

La clave se pide por teclado y no se muestra. Para un guion sin teclado se puede pasar en la
variable de entorno USUARIO_CLAVE.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.acceso import ROLES, cifrar_clave, validar_clave_nueva
from app.models import Usuario


def _buscar(session: Session, email: str) -> Usuario | None:
    return session.scalar(select(Usuario).where(func.lower(Usuario.email) == email.strip().lower()))


def crear_usuario(session: Session, nombre: str, email: str, rol: str, clave: str) -> Usuario:
    if rol not in ROLES:
        raise ValueError(f"El rol debe ser uno de: {', '.join(ROLES)}")
    validar_clave_nueva(clave)
    email = email.strip().lower()
    if _buscar(session, email) is not None:
        raise ValueError("Ya existe un usuario con ese correo")
    usuario = Usuario(
        nombre=nombre.strip(), email=email, rol=rol, activo=True, clave_hash=cifrar_clave(clave)
    )
    session.add(usuario)
    session.commit()
    return usuario


def cambiar_clave(session: Session, email: str, clave: str) -> Usuario:
    validar_clave_nueva(clave)
    usuario = _buscar(session, email)
    if usuario is None:
        raise ValueError("No existe un usuario con ese correo")
    usuario.clave_hash = cifrar_clave(clave)
    session.commit()
    return usuario


def activar(session: Session, email: str, activo: bool) -> Usuario:
    usuario = _buscar(session, email)
    if usuario is None:
        raise ValueError("No existe un usuario con ese correo")
    usuario.activo = activo
    session.commit()
    return usuario


def _pedir_clave() -> str:
    clave = os.getenv("USUARIO_CLAVE")
    if clave:
        return clave
    clave = getpass.getpass("Clave: ")
    if clave != getpass.getpass("Repite la clave: "):
        raise ValueError("Las claves no coinciden")
    return clave


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Usuarios del panel de Joyería Xavier")
    comandos = parser.add_subparsers(dest="comando", required=True)
    crear = comandos.add_parser("crear")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--email", required=True)
    crear.add_argument("--rol", required=True, choices=ROLES)
    for nombre in ("clave", "desactivar", "activar"):
        comandos.add_parser(nombre).add_argument("--email", required=True)
    comandos.add_parser("listar")
    args = parser.parse_args(argumentos)

    from app.db import SessionLocal

    with SessionLocal() as session:
        try:
            if args.comando == "crear":
                u = crear_usuario(session, args.nombre, args.email, args.rol, _pedir_clave())
                print(f"Usuario creado: {u.email} ({u.rol})")
            elif args.comando == "clave":
                u = cambiar_clave(session, args.email, _pedir_clave())
                print(f"Clave actualizada: {u.email}")
            elif args.comando in ("desactivar", "activar"):
                u = activar(session, args.email, args.comando == "activar")
                print(f"{u.email}: {'activo' if u.activo else 'desactivado'}")
            else:
                for u in session.scalars(select(Usuario).order_by(Usuario.id)):
                    estado = "activo" if u.activo else "desactivado"
                    acceso = "con clave" if u.clave_hash else "sin clave"
                    print(f"{u.id}\t{u.email}\t{u.rol}\t{estado}\t{acceso}")
        except ValueError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
