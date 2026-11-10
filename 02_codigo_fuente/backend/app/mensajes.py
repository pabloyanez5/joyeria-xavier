"""Mensajes salientes con formato (texto, botones, listas, imágenes) independientes del canal.

El agente arma estos mensajes; cada canal decide cómo mostrarlos. WhatsApp los muestra
como botones, listas o fotos; los canales que no los soportan reciben `plano()`.
"""
from dataclasses import dataclass, field

# Límites de la API de WhatsApp Cloud para mensajes interactivos.
MAX_BOTONES = 3
MAX_FILAS = 10
LARGO_BOTON = 20
LARGO_FILA = 24
LARGO_DESCRIPCION = 72
LARGO_CUERPO = 1024


def cortar(texto: str, largo: int) -> str:
    """Recorta a `largo` caracteres agregando … si hizo falta."""
    texto = " ".join(texto.split())
    return texto if len(texto) <= largo else texto[: largo - 1].rstrip() + "…"


@dataclass
class Boton:
    id: str
    titulo: str


@dataclass
class Fila:
    id: str
    titulo: str
    descripcion: str | None = None


@dataclass
class Saliente:
    tipo: str  # "texto" | "botones" | "lista" | "imagen"
    texto: str
    botones: list[Boton] = field(default_factory=list)
    filas: list[Fila] = field(default_factory=list)
    etiqueta_lista: str = "Ver opciones"
    imagen_url: str | None = None

    def plano(self) -> str:
        """Versión solo texto, para canales sin botones ni listas."""
        if self.tipo == "botones":
            opciones = [b.titulo for b in self.botones]
        elif self.tipo == "lista":
            opciones = [
                f.titulo + (f" · {f.descripcion}" if f.descripcion else "")
                for f in self.filas
            ]
        elif self.tipo == "imagen" and self.imagen_url:
            return f"{self.texto}\n{self.imagen_url}"
        else:
            return self.texto
        return self.texto + "\n" + "\n".join(f"• {o}" for o in opciones)


def texto(cuerpo: str) -> Saliente:
    return Saliente("texto", cuerpo)


def botones(cuerpo: str, opciones: list[Boton]) -> Saliente:
    return Saliente("botones", cuerpo, botones=opciones[:MAX_BOTONES])


def lista(cuerpo: str, filas: list[Fila], etiqueta: str = "Ver opciones") -> Saliente:
    return Saliente("lista", cuerpo, filas=filas[:MAX_FILAS], etiqueta_lista=etiqueta)


def imagen(url: str, pie: str) -> Saliente:
    return Saliente("imagen", pie, imagen_url=url)
