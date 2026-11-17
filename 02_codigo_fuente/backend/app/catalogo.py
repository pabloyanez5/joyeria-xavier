from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Precio, Producto, TarifaMaterial

router = APIRouter(prefix="/productos", tags=["catalogo"])

CENTAVOS = Decimal("0.01")


class PrecioOut(BaseModel):
    material: str
    quilataje: str | None
    precio: Decimal


class ProductoOut(BaseModel):
    id: int
    nombre: str
    categoria: str
    descripcion: str | None
    imagen_url: str | None = None
    precios: list[PrecioOut]
    precio_desde: Decimal | None


@dataclass
class PrecioCalculado:
    """Precio de una combinación material/quilataje de un producto, ya resuelto."""

    producto_id: int
    material: str
    quilataje: str | None
    precio: Decimal
    metodo: str  # "formula" (peso x precio por gramo + mano de obra) o "tabla" (precio fijo)
    peso_gramos: Decimal | None = None
    precio_gramo: Decimal | None = None
    costo_material: Decimal | None = None
    mano_obra: Decimal | None = None


def _clave(material: str, quilataje: str | None) -> tuple[str, str]:
    return (material.lower(), (quilataje or "").lower())


def tarifas_vigentes(session: Session) -> dict[tuple[str, str], TarifaMaterial]:
    """Por material/quilataje, el precio por gramo más reciente (sin futuros)."""
    filas = session.scalars(
        select(TarifaMaterial)
        .where(TarifaMaterial.vigente_desde <= date.today())
        .order_by(TarifaMaterial.vigente_desde, TarifaMaterial.id)
    ).all()
    return {_clave(t.material, t.quilataje): t for t in filas}


def calcular_precio(
    producto: Producto, precio_tabla: Precio, tarifa: TarifaMaterial | None
) -> PrecioCalculado:
    """Fórmula: peso (g) x precio por gramo del material + mano de obra de la pieza.

    Si la pieza no tiene peso registrado o no hay tarifa vigente para el material,
    se usa el precio fijo de la tabla `precios`.
    """
    if producto.peso_gramos is not None and tarifa is not None:
        peso = Decimal(producto.peso_gramos)
        costo_material = (peso * Decimal(tarifa.precio_gramo)).quantize(
            CENTAVOS, rounding=ROUND_HALF_UP
        )
        mano_obra = Decimal(producto.mano_obra or 0).quantize(CENTAVOS)
        return PrecioCalculado(
            producto_id=producto.id,
            material=precio_tabla.material,
            quilataje=precio_tabla.quilataje,
            precio=costo_material + mano_obra,
            metodo="formula",
            peso_gramos=peso,
            precio_gramo=Decimal(tarifa.precio_gramo),
            costo_material=costo_material,
            mano_obra=mano_obra,
        )
    return PrecioCalculado(
        producto_id=producto.id,
        material=precio_tabla.material,
        quilataje=precio_tabla.quilataje,
        precio=precio_tabla.precio,
        metodo="tabla",
    )


def precios_vigentes(
    session: Session, productos: list[Producto]
) -> dict[int, list[PrecioCalculado]]:
    """Por producto, el precio de cada material/quilataje que ofrece.

    La tabla `precios` define qué combinaciones se ofrecen (y es el respaldo);
    el monto sale de la fórmula cuando la pieza tiene peso y hay tarifa vigente.
    """
    por_id = {p.id: p for p in productos}
    if not por_id:
        return {}
    filas = session.scalars(
        select(Precio)
        .where(Precio.producto_id.in_(list(por_id)), Precio.vigente_desde <= date.today())
        .order_by(Precio.vigente_desde, Precio.id)
    ).all()
    ultimos = {(p.producto_id, p.material, p.quilataje): p for p in filas}
    tarifas = tarifas_vigentes(session)
    resultado: dict[int, list[PrecioCalculado]] = {}
    for p in ultimos.values():
        tarifa = tarifas.get(_clave(p.material, p.quilataje))
        resultado.setdefault(p.producto_id, []).append(
            calcular_precio(por_id[p.producto_id], p, tarifa)
        )
    return resultado


def armar_salida(producto: Producto, precios: list[PrecioCalculado]) -> ProductoOut:
    ordenados = sorted(precios, key=lambda x: x.precio)
    return ProductoOut(
        id=producto.id,
        nombre=producto.nombre,
        categoria=producto.categoria,
        descripcion=producto.descripcion,
        imagen_url=producto.imagen_url,
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
    vigentes = precios_vigentes(session, list(productos))

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
    return armar_salida(producto, precios_vigentes(session, [producto]).get(producto.id, []))


class CotizacionOut(BaseModel):
    producto_id: int
    nombre: str
    material: str
    quilataje: str | None
    precio: Decimal
    moneda: str = "USD"
    referencial: bool = True
    # Desglose de la fórmula (vacío si el precio viene de la tabla fija).
    metodo: str = "tabla"
    peso_gramos: Decimal | None = None
    precio_gramo: Decimal | None = None
    costo_material: Decimal | None = None
    mano_obra: Decimal | None = None


def _igual(a: str | None, b: str | None) -> bool:
    return (a or "").lower() == (b or "").lower()


@router.get("/{producto_id}/cotizacion", response_model=CotizacionOut)
def cotizar(
    producto_id: int,
    material: str,
    quilataje: str | None = None,
    session: Session = Depends(get_session),
):
    producto = session.get(Producto, producto_id)
    if producto is None or not producto.activo:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for p in precios_vigentes(session, [producto]).get(producto.id, []):
        if _igual(p.material, material) and _igual(p.quilataje, quilataje):
            return CotizacionOut(
                producto_id=producto.id,
                nombre=producto.nombre,
                material=p.material,
                quilataje=p.quilataje,
                precio=p.precio,
                metodo=p.metodo,
                peso_gramos=p.peso_gramos,
                precio_gramo=p.precio_gramo,
                costo_material=p.costo_material,
                mano_obra=p.mano_obra,
            )
    raise HTTPException(
        status_code=422, detail="Combinación no disponible para este producto"
    )
