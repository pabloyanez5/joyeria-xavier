from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Precio, Producto

router = APIRouter(prefix="/productos", tags=["catalogo"])


class PrecioOut(BaseModel):
    material: str
    quilataje: str | None
    precio: Decimal


class ProductoOut(BaseModel):
    id: int
    nombre: str
    categoria: str
    descripcion: str | None
    precios: list[PrecioOut]
    precio_desde: Decimal | None


def precios_vigentes(session: Session, producto_ids: list[int]) -> dict[int, list[Precio]]:
    """Por producto, el precio más reciente (sin futuros) de cada material/quilataje."""
    filas = session.scalars(
        select(Precio)
        .where(Precio.producto_id.in_(producto_ids), Precio.vigente_desde <= date.today())
        .order_by(Precio.vigente_desde, Precio.id)
    ).all()
    ultimos = {(p.producto_id, p.material, p.quilataje): p for p in filas}
    resultado: dict[int, list[Precio]] = {}
    for p in ultimos.values():
        resultado.setdefault(p.producto_id, []).append(p)
    return resultado


def armar_salida(producto: Producto, precios: list[Precio]) -> ProductoOut:
    ordenados = sorted(precios, key=lambda x: x.precio)
    return ProductoOut(
        id=producto.id,
        nombre=producto.nombre,
        categoria=producto.categoria,
        descripcion=producto.descripcion,
        precios=[
            PrecioOut(material=x.material, quilataje=x.quilataje, precio=x.precio)
            for x in ordenados
        ],
        precio_desde=ordenados[0].precio if ordenados else None,
    )


@router.get("", response_model=list[ProductoOut])
def listar_productos(
    categoria: str | None = None,
    material: str | None = None,
    q: str | None = None,
    precio_min: Decimal | None = None,
    precio_max: Decimal | None = None,
    limite: int = Query(20, ge=1, le=100),
    desde: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    consulta = select(Producto).where(Producto.activo.is_(True)).order_by(Producto.id)
    if categoria:
        consulta = consulta.where(func.lower(Producto.categoria) == categoria.lower())
    if q:
        consulta = consulta.where(Producto.nombre.ilike(f"%{q}%"))
    productos = session.scalars(consulta).all()
    vigentes = precios_vigentes(session, [p.id for p in productos])

    filtra_precio = bool(material) or precio_min is not None or precio_max is not None
    salida = []
    for producto in productos:
        precios = vigentes.get(producto.id, [])
        if material:
            precios = [x for x in precios if x.material.lower() == material.lower()]
        if precio_min is not None:
            precios = [x for x in precios if x.precio >= precio_min]
        if precio_max is not None:
            precios = [x for x in precios if x.precio <= precio_max]
        if filtra_precio and not precios:
            continue
        salida.append(armar_salida(producto, precios))
    return salida[desde : desde + limite]


@router.get("/categorias", response_model=list[str])
def listar_categorias(session: Session = Depends(get_session)):
    return list(
        session.scalars(
            select(Producto.categoria)
            .where(Producto.activo.is_(True))
            .distinct()
            .order_by(Producto.categoria)
        )
    )


@router.get("/{producto_id}", response_model=ProductoOut)
def detalle_producto(producto_id: int, session: Session = Depends(get_session)):
    producto = session.get(Producto, producto_id)
    if producto is None or not producto.activo:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return armar_salida(producto, precios_vigentes(session, [producto.id]).get(producto.id, []))