"""Estado de las órdenes de un cliente, contado para él (JOY-21).

Lo usan el agente con modelo (herramienta consultar_orden) y el motor de reglas, para que el
cliente reciba el estado de su pedido aunque el modelo no responda.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Orden, Producto

# Cómo se le cuenta al cliente cada etapa de su orden.
ETAPA_PARA_EL_CLIENTE = {
    "por_verificar": "pendiente de confirmar el abono con un asesor",
    "en_cola": "confirmada, en la cola del taller",
    "en_produccion": "en producción",
    "terminada": "terminada, lista para coordinar la entrega",
    "entregada": "entregada",
}

MAXIMO = 5


def etapa(orden: Orden) -> str:
    return ETAPA_PARA_EL_CLIENTE.get(orden.etapa_actual, orden.etapa_actual.replace("_", " "))


def vigentes(session: Session, cliente_id: int) -> list[Orden]:
    """Las órdenes que aún no se entregan (las más recientes primero). Si ya se entregaron
    todas, la última entregada, para que el cliente sepa que su pedido se cerró."""
    abiertas = list(
        session.scalars(
            select(Orden)
            .where(Orden.cliente_id == cliente_id, Orden.etapa_actual != "entregada")
            .order_by(Orden.id.desc())
            .limit(MAXIMO)
        )
    )
    if abiertas:
        return abiertas
    ultima = session.scalar(
        select(Orden).where(Orden.cliente_id == cliente_id).order_by(Orden.id.desc())
    )
    return [ultima] if ultima else []


def _joya(session: Session, orden: Orden) -> str:
    producto = session.get(Producto, orden.producto_id) if orden.producto_id else None
    if producto is not None:
        return producto.nombre
    corta = orden.descripcion.split(". Origen:")[0].strip()
    return corta if len(corta) <= 60 else corta[:57].rstrip() + "…"


def _entrega(orden: Orden) -> str:
    if orden.fecha_entrega_cliente and orden.etapa_actual != "entregada":
        return f" Entrega estimada: {orden.fecha_entrega_cliente:%d/%m/%Y}."
    return ""


def para_el_agente(session: Session, cliente_id: int) -> str:
    """Lo que devuelve la herramienta consultar_orden."""
    ordenes = vigentes(session, cliente_id)
    if not ordenes:
        return (
            "El cliente no tiene órdenes registradas. Si insiste en que hizo un pedido, "
            "derívalo a un asesor para que lo busque."
        )
    lineas = [
        f"- OP-{o.id:06d}: {o.descripcion} · etapa actual: {etapa(o)}.{_entrega(o)}"
        for o in ordenes
    ]
    return "Órdenes del cliente:\n" + "\n".join(lineas)


def para_el_cliente(session: Session, cliente_id: int, nombre: str | None) -> str | None:
    """Respuesta lista para enviar. None si el cliente no tiene órdenes."""
    ordenes = vigentes(session, cliente_id)
    if not ordenes:
        return None
    coma = f", {nombre}" if nombre else ""
    lineas = [
        f"• OP-{o.id:06d} · {_joya(session, o)}: {etapa(o)}.{_entrega(o)}" for o in ordenes
    ]
    plural = "tus pedidos" if len(ordenes) > 1 else "tu pedido"
    return (
        f"Esto es lo que tengo de {plural}{coma}:\n"
        + "\n".join(lineas)
        + "\nTe avisaré por aquí cada vez que avance. Si necesitas algo más, escribe «asesor»."
    )
