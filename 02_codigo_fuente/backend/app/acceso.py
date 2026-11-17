"""Inicio de sesión y control de acceso por rol (JOY-78, RNF-01 y RNF-09).

- Las claves se guardan con PBKDF2-HMAC-SHA256 y una sal por usuario; nunca en texto plano.
- La sesión es un token firmado (JWT HS256) que caduca; el rol se lee de la base en cada
  petición, así que desactivar a un usuario o cambiarle el rol tiene efecto inmediato.
- Cada operación del panel declara qué roles la pueden usar con `requiere(...)`.
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cache import get_redis
from app.db import get_session
from app.models import Usuario

logger = logging.getLogger("joyeria.acceso")

router = APIRouter(prefix="/sesion", tags=["sesion"])

ROLES = ("asesor", "taller", "direccion", "admin")
ALGORITMO = "HS256"
HORAS_DE_SESION = 8  # una jornada de trabajo
LARGO_MINIMO_DE_CLAVE = 10

# --- claves ---

ITERACIONES = 600_000  # recomendación de OWASP para PBKDF2-HMAC-SHA256
_FORMATO = "pbkdf2_sha256"


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def cifrar_clave(clave: str, iteraciones: int | None = None) -> str:
    """Devuelve la clave lista para guardar: formato$iteraciones$sal$resumen."""
    iteraciones = iteraciones or ITERACIONES
    sal = secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, iteraciones)
    return f"{_FORMATO}${iteraciones}${_b64(sal)}${_b64(resumen)}"


def clave_correcta(clave: str, guardada: str | None) -> bool:
    if not guardada:
        return False
    try:
        formato, iteraciones, sal, resumen = guardada.split("$")
        if formato != _FORMATO:
            return False
        calculado = hashlib.pbkdf2_hmac(
            "sha256", clave.encode("utf-8"), base64.b64decode(sal), int(iteraciones)
        )
        return hmac.compare_digest(calculado, base64.b64decode(resumen))
    except (ValueError, TypeError):
        return False


def validar_clave_nueva(clave: str) -> None:
    if len(clave) < LARGO_MINIMO_DE_CLAVE:
        raise ValueError(f"La clave debe tener al menos {LARGO_MINIMO_DE_CLAVE} caracteres")


# --- token de sesión ---

@lru_cache
def _secreto_temporal() -> str:
    logger.warning(
        "Falta SESION_SECRETO (mínimo 32 caracteres): se usa uno temporal y las sesiones "
        "se cierran al reiniciar el servidor"
    )
    return secrets.token_urlsafe(48)


def _secreto() -> str:
    valor = os.getenv("SESION_SECRETO", "").strip()
    return valor if len(valor) >= 32 else _secreto_temporal()


def crear_token(usuario: Usuario, ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now(timezone.utc)
    datos = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "iat": ahora,
        "exp": ahora + timedelta(hours=HORAS_DE_SESION),
    }
    return jwt.encode(datos, _secreto(), algorithm=ALGORITMO)


def leer_token(token: str) -> dict | None:
    """Los datos del token si la firma es válida y no caducó; si no, None."""
    try:
        return jwt.decode(
            token, _secreto(), algorithms=[ALGORITMO], options={"require": ["exp", "sub"]}
        )
    except jwt.InvalidTokenError:
        return None


# --- quién hace la petición ---

_portador = HTTPBearer(auto_error=False)
_SIN_SESION = HTTPException(
    401, "Inicia sesión para continuar", headers={"WWW-Authenticate": "Bearer"}
)


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_portador),
    session: Session = Depends(get_session),
) -> Usuario:
    if credenciales is None:
        raise _SIN_SESION
    datos = leer_token(credenciales.credentials)
    if datos is None or not str(datos.get("sub", "")).isdigit():
        raise _SIN_SESION
    usuario = session.get(Usuario, int(datos["sub"]))
    if usuario is None or not usuario.activo:
        raise _SIN_SESION
    return usuario


def requiere(*roles: str):
    """Dependencia que deja pasar solo a esos roles (el rol admin pasa siempre)."""
    permitidos = set(roles) | {"admin"}

    def verificar(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol not in permitidos:
            raise HTTPException(403, "Tu rol no tiene permiso para esta operación")
        return usuario

    return verificar


# --- freno a los intentos de adivinar una clave ---

MAX_FALLOS = 5
MINUTOS_DE_BLOQUEO = 15


class Intentos:
    """Cuenta los fallos de inicio de sesión por correo. Si Redis falla, no bloquea a nadie."""

    def __init__(self, cliente_redis):
        self.redis = cliente_redis

    @staticmethod
    def _clave(email: str) -> str:
        return "sesion:fallos:" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]

    def bloqueado(self, email: str) -> bool:
        try:
            return int(self.redis.get(self._clave(email)) or 0) >= MAX_FALLOS
        except redis.RedisError:
            return False

    def fallo(self, email: str) -> None:
        try:
            clave = self._clave(email)
            if self.redis.incr(clave) == 1:
                self.redis.expire(clave, MINUTOS_DE_BLOQUEO * 60)
        except redis.RedisError:
            pass

    def limpiar(self, email: str) -> None:
        try:
            self.redis.delete(self._clave(email))
        except redis.RedisError:
            pass


def get_intentos() -> Intentos:
    return Intentos(get_redis())


# --- rutas ---

class CredencialesIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    clave: str = Field(min_length=1, max_length=200)


class UsuarioOut(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str


class SesionOut(BaseModel):
    token: str
    tipo: str = "Bearer"
    expira_en: int  # segundos
    usuario: UsuarioOut


def _salida(usuario: Usuario) -> UsuarioOut:
    return UsuarioOut(id=usuario.id, nombre=usuario.nombre, email=usuario.email, rol=usuario.rol)


# Se compara contra esta clave cuando el correo no existe, para que la respuesta tarde lo mismo
# y no revele qué correos están registrados.
@lru_cache
def _clave_de_relleno() -> str:
    return cifrar_clave(secrets.token_urlsafe(16))


@router.post("", response_model=SesionOut)
def iniciar_sesion(
    datos: CredencialesIn,
    session: Session = Depends(get_session),
    intentos: Intentos = Depends(get_intentos),
):
    email = datos.email.strip().lower()
    if intentos.bloqueado(email):
        raise HTTPException(
            429, f"Demasiados intentos. Vuelve a probar en {MINUTOS_DE_BLOQUEO} minutos."
        )
    usuario = session.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    guardada = usuario.clave_hash if usuario is not None else None
    correcta = clave_correcta(datos.clave, guardada or _clave_de_relleno())
    if usuario is None or not guardada or not correcta or not usuario.activo:
        intentos.fallo(email)
        logger.warning("Inicio de sesión rechazado")
        raise HTTPException(401, "Correo o clave incorrectos")
    intentos.limpiar(email)
    return SesionOut(
        token=crear_token(usuario), expira_en=HORAS_DE_SESION * 3600, usuario=_salida(usuario)
    )


@router.get("", response_model=UsuarioOut)
def sesion_actual(usuario: Usuario = Depends(usuario_actual)):
    return _salida(usuario)
