"""Respuestas interactivas del agente: botones, listas y fotos del catálogo.

Las opciones que el cliente toca llegan como una `accion` (por ejemplo `cat:Anillos` o
`prod:3`) y se resuelven aquí sin necesidad de interpretar texto libre.
"""
from decimal import Decimal
from urllib.parse import quote, urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalogo import precios_vigentes
from app.mensajes import Boton, Fila, Saliente, botones, imagen, lista, tarjeta, texto
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


MAX_FOTOS = 3  # fotos por categoría, para no llenar el chat


def _url_de_foto(producto: Producto, base_media: str) -> str | None:
    if not producto.imagen_url:
        return None
    url = producto.imagen_url
    if not url.startswith("http"):
        url = base_media.rstrip("/") + "/" + url.lstrip("/")
    return url


def fotos_de_productos(session: Session, categoria: str, base_media: str) -> list[Saliente]:
    """Una tarjeta por joya, con su foto, nombre y precio "desde", para ver antes de elegir.

    Se muestran hasta MAX_FOTOS. Si varias joyas comparten la misma foto (las provisionales son
    una por categoría), se manda solo una vez: repetirla no ayuda a elegir."""
    productos = _productos(session, categoria)
    vigentes = precios_vigentes(session, productos)
    tarjetas, vistas = [], set()
    for p in productos:
        url = _url_de_foto(p, base_media)
        if url is None or url in vistas:
            continue
        vistas.add(url)
        desde = min((x.precio for x in vigentes.get(p.id, [])), default=None)
        cuerpo = f"*{p.nombre}*" + (f"\nDesde {_dinero(desde)}" if desde is not None else "")
        tarjetas.append(
            tarjeta(
                url,
                cuerpo,
                [Boton(f"prod:{p.id}", "Ver detalle"), Boton(f"precios:{p.id}", "Ver precios")],
            )
        )
        if len(tarjetas) == MAX_FOTOS:
            break
    return tarjetas


def vitrina(session: Session, categoria: str, cuerpo: str, base_media: str) -> list[Saliente]:
    """La lista de joyas de una categoría seguida de sus fotos con precio."""
    elegida = lista_de_productos(session, categoria, cuerpo)
    if elegida is None:
        return []
    return [elegida, *fotos_de_productos(session, categoria, base_media)]


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
    url = _url_de_foto(producto, base_media)
    if url:
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


def enlace_del_catalogo(base_web: str, contexto: dict) -> str:
    """Enlace a la web, ya filtrado por la joya y el material que el cliente mencionó."""
    params = {k: contexto[k] for k in ("categoria", "material") if contexto.get(k)}
    return base_web.rstrip("/") + (f"/?{urlencode(params)}" if params else "")


def enriquecer(
    session: Session, intencion: str, respuesta: str, nombre: str | None, contexto: dict,
    base_web: str, base_media: str = "",
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
            elegidas = vitrina(session, categoria, cuerpo, base_media or base_web)
        else:
            cuerpo = f"Claro{coma}. ¿Qué tipo de joya quieres {accion}?"
            elegidas = [m for m in [lista_de_categorias(session, cuerpo)] if m is not None]
        if elegidas:
            # La lista no admite enlaces: el del catálogo va en un mensaje aparte, para que el
            # cliente lo reciba siempre (antes solo quedaba en el panel).
            enlace = enlace_del_catalogo(base_web, contexto)
            return [*elegidas, texto(f"También puedes ver todo el catálogo y cotizar aquí: {enlace}")]
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
            elegidas = vitrina(
                session, categoria, f"Estas son nuestras joyas de {categoria.lower()}. Elige una.",
                base_media,
            )
            if elegidas:
                return elegidas, False
    if tipo in ("prod", "precios") and valor.isdigit():
        if tipo == "prod":
            return ficha_de_producto(session, int(valor), base_media), False
        return precios_de_producto(session, int(valor), base_web), False
    return [botones("¿Qué te gustaría hacer?", BOTONES_INICIO)], False


def categoria_de_accion(accion: str) -> str | None:
    """Si la acción es elegir una categoría, devuelve su nombre."""
    tipo, _, valor = accion.partition(":")
    return valor if tipo == "cat" and valor else None


def interes_de_accion(session: Session, accion: str) -> dict | None:
    """Lo que el cliente dejó ver al tocar: una categoría o una joya concreta (su modelo)."""
    tipo, _, valor = accion.partition(":")
    if tipo == "cat" and valor:
        return {"categoria": valor}
    if tipo in ("prod", "precios") and valor.isdigit():
        producto = session.get(Producto, int(valor))
        if producto is not None and producto.activo:
            return {"categoria": producto.categoria, "modelo": producto.nombre}
    return None

