"""Messenger e Instagram: la foto de la joya llega como imagen y las opciones se pueden tocar."""
import json

import pytest

from app import meta_envio
from app.mensajes import Boton, Fila, botones, imagen, lista, tarjeta, texto
from app.meta_envio import EnviadorMeta
from app.webhook import extraer_mensajes

FOTO = "https://joyeria.test/img/aretes.png"


@pytest.fixture
def enviados(monkeypatch):
    cuerpos = []

    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def falso(peticion, timeout):
        cuerpos.append(json.loads(peticion.data))
        return Respuesta()

    monkeypatch.setattr(meta_envio.urllib.request, "urlopen", falso)
    return cuerpos


def _pagina():
    return EnviadorMeta("t", "1", page_id="9", page_token="p")


@pytest.mark.parametrize("canal", ["messenger", "instagram"])
def test_la_tarjeta_manda_la_foto_y_luego_el_texto_con_sus_opciones(enviados, canal):
    s = tarjeta(FOTO, "Aretes de argolla\nDesde $41.20", [Boton("prod:5", "Ver detalle"), Boton("precios:5", "Ver precios")])
    assert _pagina().enviar_saliente(canal, "psid", s) is True

    foto, cuerpo = (c["message"] for c in enviados)
    assert foto == {"attachment": {"type": "image", "payload": {"url": FOTO}}}
    assert cuerpo["text"] == "Aretes de argolla\nDesde $41.20"
    assert FOTO not in cuerpo["text"]  # ya no llega como enlace suelto
    assert cuerpo["quick_replies"] == [
        {"content_type": "text", "title": "Ver detalle", "payload": "prod:5"},
        {"content_type": "text", "title": "Ver precios", "payload": "precios:5"},
    ]


def test_una_imagen_sola_lleva_su_pie(enviados):
    _pagina().enviar_saliente("messenger", "psid", imagen(FOTO, "Así se ve"))
    assert [c["message"] for c in enviados] == [
        {"attachment": {"type": "image", "payload": {"url": FOTO}}},
        {"text": "Así se ve"},
    ]


def test_los_botones_son_respuestas_rapidas(enviados):
    _pagina().enviar_saliente("messenger", "psid", botones("¿Oro o plata?", [Boton("m:oro", "Oro"), Boton("m:plata", "Plata")]))
    (cuerpo,) = (c["message"] for c in enviados)
    assert cuerpo["text"] == "¿Oro o plata?"
    assert [q["payload"] for q in cuerpo["quick_replies"]] == ["m:oro", "m:plata"]


def test_la_lista_se_escribe_completa_y_cada_opcion_se_puede_tocar(enviados):
    filas = [Fila("cat:aretes", "Aretes", "Desde $41.20"), Fila("cat:anillos", "Anillos de compromiso con halo")]
    _pagina().enviar_saliente("instagram", "psid", lista("Elige una categoría", filas))
    (cuerpo,) = (c["message"] for c in enviados)
    assert "Aretes · Desde $41.20" in cuerpo["text"]
    assert [q["title"] for q in cuerpo["quick_replies"]] == ["Aretes", "Anillos de compromi…"]
    assert all(len(q["title"]) <= 20 for q in cuerpo["quick_replies"])


def test_un_texto_simple_no_cambia(enviados):
    _pagina().enviar_saliente("messenger", "psid", texto("Hola"))
    assert [c["message"] for c in enviados] == [{"text": "Hola"}]


def test_whatsapp_sigue_igual(enviados):
    _pagina().enviar_saliente("whatsapp", "593", tarjeta(FOTO, "Aretes", [Boton("prod:5", "Ver detalle")]))
    (cuerpo,) = enviados
    assert cuerpo["interactive"]["header"]["image"]["link"] == FOTO


@pytest.mark.parametrize("objeto, canal", [("page", "messenger"), ("instagram", "instagram")])
def test_la_respuesta_rapida_llega_con_el_id_de_la_opcion(objeto, canal):
    payload = {
        "object": objeto,
        "entry": [{"messaging": [{
            "sender": {"id": "psid-1"},
            "message": {"mid": "m1", "text": "Ver detalle", "quick_reply": {"payload": "prod:5"}},
        }]}],
    }
    (m,) = extraer_mensajes(payload)
    assert (m.canal, m.texto, m.accion) == (canal, "Ver detalle", "prod:5")


def test_un_mensaje_escrito_no_trae_accion():
    payload = {"object": "page", "entry": [{"messaging": [{"sender": {"id": "p"}, "message": {"mid": "m", "text": "hola"}}]}]}
    (m,) = extraer_mensajes(payload)
    assert m.accion is None
