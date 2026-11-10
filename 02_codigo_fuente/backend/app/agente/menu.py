"""Respuestas interactivas del agente: botones, listas y fotos del catálogo.

Las opciones que el cliente toca llegan como una `accion` (por ejemplo `cat:Anillos` o
`prod:3`) y se resuelven aquí sin necesidad de interpretar texto libre.
"""
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalogo import precios_vigentes
from app.mensajes import Boton, Fila, Saliente, botones, imagen, lista, texto
from app.models import Producto

BOTONES_INICIO = [
    Boton("menu:cotizar", "Cotizar una joya"),
    Boton("menu:catalogo", "Ver catálogo"),
    Boton("menu:asesor", "Hablar con asesor"),
]

TEXTO_ASESOR = "Claro, te comunico con un asesor. En breve te atenderá una persona."


def _dinero(valor: Decimal) -> str:
    return f"${Decimal(valor):,.2f}"


def _etiqueta(material: str, quilataje: str | None) -> str:
    return f"{material.capitalize()} {quilataje or ''}".strip()


def _categorias(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(Producto.categoria)
            .where(Producto.activo.is_(True))
            .distinct()
            .order_by(Producto.categoria)
        )
    )


def _categoria_existente(session: Session, nombre: str) -> str | None:
    for categoria in _categorias(session):
        if categoria.lower() == nombre.lower():
            return categoria
    return None


def _productos(session: Session, categoria: str) -> list[Producto]:
    return list(
        session.scalars(
            select(Producto)
            .where(
                Producto.activo.is_(True),
                func.lower(Producto.categoria) == categoria.lower(),
            )
            .order_by(Producto.id)
        )
    )


def lista_de_categorias(session: Session, cuerpo: str) -> Saliente | None:
    categorias = _categorias(session)
    if not categorias:
        return None
    return lista(
        cuerpo,
        [Fila(f"cat:{c}", c) for c in categorias],
        etiqueta="Elegir tipo",
    )


def lista_de_productos(session: Session, categoria: str, cuerpo: str) -> Saliente | None:
    productos = _productos(session, categoria)
    if not productos:
        return None
    vigentes = precios_vigentes(session, productos)
    filas = []
    for p in productos:
        precios = vigentes.get(p.id, [])
        desde = min((x.precio for x in precios), default=None)
        filas.append(
            Fila(
                f"prod:{p.id}",
                p.nombre,
                f"Desde {_dinero(desde)}" if desde is not None else None,
            )
        )
    return lista(cuerpo, filas, etiqueta="Ver joyas")


def ficha_de_producto(session: Session, producto_id: int, base_media: str) -> list[Saliente]:
    producto = session.get(Producto, producto_id)
    if producto is None or not producto.activo:
        return [botones("Esa joya ya no está disponible. ¿Qué quieres hacer?", BOTONES_INICIO)]
    precios = precios_vigentes(session, [producto]).get(producto.id, [])
    desde = min((x.precio for x in precios), default=None)
    pie = f"*{producto.nombre}*"
    if producto.descripcion:
        pie += f"\n{producto.descripcion}"
    if desde is not None:
        pie += f"\nDesde {_dinero(desde)}"
    opciones = botones(
        "¿Quieres ver el precio detallado?",
        [
            Boton(f"precios:{producto.id}", "Ver precios"),
            Boton("menu:catalogo", "Otra joya"),
            Boton("menu:asesor", "Hablar con asesor"),
        ],
    )
    if producto.imagen_url:
        url = producto.imagen_url
        if not url.startswith("http"):
            url = base_media.rstrip("/") + "/" + url.lstrip("/")
        return [imagen(url, pie), opciones]
    return [botones(pie + "\n\n¿Quieres ver el precio detallado?", opciones.botones)]


def precios_de_producto(session: Session, producto_id: int, base_web: str) -> list[Saliente]:
    producto = session.get(Producto, producto_id)
    if producto is None or not producto.activo:
        return [botones("Esa joya ya no está disponible. ¿Qué quieres hacer?", BOTONES_INICIO)]
    precios = sorted(
        precios_vigentes(session, [producto]).get(producto.id, []), key=lambda x: x.precio
    )
    lineas = [f"*{producto.nombre}*: precio referencial en USD", ""]
    for p in precios:
        linea = f"• {_etiqueta(p.material, p.quilataje)}: *{_dinero(p.precio)}*"
        if p.metodo == "formula":
            linea += (
                f" ({float(p.peso_gramos):g} g × {_dinero(p.precio_gramo)}/g"
                f" + {_dinero(p.mano_obra)} de mano de obra)"
            )
        lineas.append(linea)
    enlace = f"{base_web.rstrip('/')}/?categoria={quote(producto.categoria)}"
    lineas += [
        "",
        "Es un valor referencial; un asesor confirma el precio final.",
        f"Puedes configurarla y ajustarla en la web: {enlace}",
    ]
    return [
        texto("\n".join(lineas)),
        botones(
            "¿Qué quieres hacer ahora?",
            [Boton("menu:catalogo", "Otra joya"), Boton("menu:asesor", "Hablar con asesor")],
        ),
    ]


def enriquecer(
    session: Session, intencion: str, respuesta: str, nombre: str | None, contexto: dict,
    base_web: str,
) -> list[Saliente]:
    """Convierte la respuesta de texto del agente en un mensaje con botones o lista."""
    if intencion in ("saludo", "otro"):
        return [botones(respuesta, BOTONES_INICIO)]
    if intencion in ("cotizar", "catalogo"):
        coma = f", {nombre}" if nombre else ""
        categoria = contexto.get("categoria") and _categoria_existente(
            session, contexto["categoria"]
        )
        accion = "cotizar" if intencion == "cotizar" else "ver"
        if categoria:
            cuerpo = f"Claro{coma}. Estas son nuestras joyas de {categoria.lower()}; elige la que quieres {accion}."
            elegida = lista_de_productos(session, categoria, cuerpo)
        else:
            cuerpo = f"Claro{coma}. ¿Qué tipo de joya quieres {accion}?"
            elegida = lista_de_categorias(session, cuerpo)
        if elegida is not None:
            return [elegida]
    return [texto(respuesta)]


def responder_accion(
    session: Session, accion: str, base_web: str, base_media: str
) -> tuple[list[Saliente], bool]:
    """Resuelve lo que el cliente tocó. Devuelve (mensajes, si pasa a un asesor)."""
    tipo, _, valor = accion.partition(":")
    if tipo == "menu" and valor == "asesor":
        return [texto(TEXTO_ASESOR)], True
    if tipo == "menu" and valor in ("cotizar", "catalogo"):
        verbo = "cotizar" if valor == "cotizar" else "ver"
        elegida = lista_de_categorias(session, f"¿Qué tipo de joya quieres {verbo}?")
        if elegida is not None:
            return [elegida], False
    if tipo == "cat":
        categoria = _categoria_existente(session, valor)
        if categoria:
            elegida = lista_de_productos(
                session, categoria, f"Estas son nuestras joyas de {categoria.lower()}. Elige una."
            )
            if elegida is not None:
                return [elegida], False
    if tipo in ("prod", "precios") and valor.isdigit():
        if tipo == "prod":
            return ficha_de_producto(session, int(valor), base_media), False
        return precios_de_producto(session, int(valor), base_web), False
    return [botones("¿Qué te gustaría hacer?", BOTONES_INICIO)], False


def categoria_de_accion(accion: str) -> str | None:
    """Si la acción es elegir una categoría, devuelve su nombre."""
    tipo, _, valor = accion.partition(":")
    return valor if tipo == "cat" and valor else None

