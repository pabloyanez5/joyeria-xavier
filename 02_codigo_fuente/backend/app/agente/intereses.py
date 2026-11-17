"""Intereses del cliente (JOY-80): cada joya que pide es un interés aparte, con sus propios datos.

Antes la ficha guardaba una sola joya y, si el cliente pedía otra, los datos se pisaban (el
presupuesto de la cadena terminaba en los aretes). Ahora el contexto del cliente lleva:

    {"intereses": [{"categoria": "Aretes", "presupuesto": "400"}, {"categoria": "Cadenas", ...}],
     "activo": 1,                       # de cuál se está hablando
     "categoria": "Cadenas", ...}       # copia del interés activo

La copia del interés activo mantiene funcionando lo que ya leía esas claves (el enlace al
catálogo, el motor de reglas y el menú).
"""

# Datos propios de cada joya.
CAMPOS = ("categoria", "material", "quilataje", "modelo", "talla", "ocasion", "presupuesto")
# Los que además se copian arriba del contexto, por compatibilidad.
_ESPEJO = ("categoria", "material", "quilataje", "ocasion", "presupuesto")
MAXIMO = 8  # tope de intereses por cliente, para que un mensaje raro no llene la ficha

ETIQUETAS = (
    ("categoria", "Joya"),
    ("modelo", "Modelo"),
    ("material", "Material"),
    ("quilataje", "Quilataje"),
    ("talla", "Talla"),
    ("ocasion", "Ocasión"),
    ("presupuesto", "Presupuesto"),
)


def lista(contexto: dict | None) -> list[dict]:
    """Los intereses guardados. Una ficha antigua (una sola joya) cuenta como un interés."""
    contexto = contexto or {}
    guardados = contexto.get("intereses")
    if isinstance(guardados, list):
        return [dict(i) for i in guardados if isinstance(i, dict)]
    antiguo = {c: contexto[c] for c in CAMPOS if contexto.get(c)}
    return [antiguo] if antiguo else []


def indice_activo(contexto: dict | None) -> int | None:
    intereses = lista(contexto)
    if not intereses:
        return None
    indice = (contexto or {}).get("activo")
    return indice if isinstance(indice, int) and 0 <= indice < len(intereses) else len(intereses) - 1


def activo(contexto: dict | None) -> dict | None:
    indice = indice_activo(contexto)
    return lista(contexto)[indice] if indice is not None else None


def _igual(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and str(a).strip().casefold() == str(b).strip().casefold()


def anotar(contexto: dict | None, otra_joya: bool = False, **datos) -> dict:
    """Devuelve el contexto con los datos puestos en el interés que corresponde.

    - Si viene la categoría de una joya que ya estaba, se retoma ese interés.
    - Si viene una categoría nueva (o `otra_joya`), se abre un interés aparte.
    - Sin categoría, los datos son del interés del que se está hablando.
    """
    contexto = dict(contexto or {})
    datos = {c: str(v).strip() for c, v in datos.items() if c in CAMPOS and v and str(v).strip()}
    if not datos and not otra_joya:
        return contexto
    intereses = lista(contexto)
    indice = indice_activo(contexto)

    categoria = datos.get("categoria")
    if otra_joya:
        indice = None
    elif categoria:
        mismo = next((n for n, i in enumerate(intereses) if _igual(i.get("categoria"), categoria)), None)
        if mismo is not None:
            indice = mismo
            datos.pop("categoria")  # se conserva como ya estaba escrita
        elif indice is not None and intereses[indice].get("categoria"):
            indice = None  # el interés activo es de otra joya: este va aparte
    if indice is None:
        if len(intereses) >= MAXIMO:
            return contexto
        intereses.append({})
        indice = len(intereses) - 1
    intereses[indice].update(datos)

    contexto["intereses"] = intereses
    contexto["activo"] = indice
    for campo in _ESPEJO:
        if intereses[indice].get(campo):
            contexto[campo] = intereses[indice][campo]
        else:
            contexto.pop(campo, None)
    return contexto


def titulo(interes: dict) -> str:
    """'Aretes de oro', 'Cadenas' o 'Joya sin definir'."""
    texto = interes.get("categoria") or "Joya sin definir"
    if interes.get("material"):
        texto += f" de {interes['material']}"
    return texto


def describir(interes: dict) -> str:
    """Una línea con todo lo que se sabe de esa joya (para el modelo y para la orden)."""
    partes = [f"{etiqueta}: {interes[c]}" for c, etiqueta in ETIQUETAS if interes.get(c)]
    return "; ".join(partes)


def resumen(contexto: dict | None) -> str:
    """Los intereses numerados, marcando de cuál se habla; texto para el modelo."""
    intereses = lista(contexto)
    if not intereses:
        return "Todavía no hay joyas anotadas."
    actual = indice_activo(contexto)
    lineas = []
    for n, interes in enumerate(intereses):
        marca = " (de esta se está hablando)" if n == actual and len(intereses) > 1 else ""
        lineas.append(f"{n + 1}. {describir(interes) or 'sin datos'}{marca}")
    return "\n".join(lineas)
