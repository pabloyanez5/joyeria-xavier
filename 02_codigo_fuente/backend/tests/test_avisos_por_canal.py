"""Los avisos de la orden salen por el canal del cliente y los rechazos de Meta se explican."""
import pytest

from app.meta_envio import Enviador, ErrorMeta
from app.models import Cliente
from app.ordenes import motivo_legible
from tests.conftest import datos_de_orden, verificar
from tests.test_etapas import api, avanzar, con_enviador, datos  # noqa: F401


class EnviadorQueRecuerda(Enviador):
    def __init__(self, error=None):
        self.enviados = []
        self.error = error

    def enviar(self, canal, destinatario, texto):
        if self.error:
            raise ErrorMeta(self.error)
        self.enviados.append((canal, destinatario, texto))
        return True


def _orden_de(api, session, canal):
    cliente = Cliente(canal=canal, id_canal="PSID-123", nombre_perfil="Ana")
    session.add(cliente)
    session.commit()
    orden = api.post("/ordenes", json=datos_de_orden(cliente_id=cliente.id, descripcion="Anillo")).json()
    return verificar(api, orden)


@pytest.mark.parametrize("canal", ["whatsapp", "messenger", "instagram"])
def test_la_orden_dice_el_canal_del_cliente(api, session, canal):
    assert _orden_de(api, session, canal)["canal"] == canal


def test_el_aviso_de_etapa_sale_por_messenger(api, session):
    orden = _orden_de(api, session, "messenger")
    enviador = EnviadorQueRecuerda()
    con_enviador(enviador)
    r = avanzar(api, orden, "en_produccion").json()
    assert r["aviso_al_cliente"] == "enviado"
    assert enviador.enviados[0][:2] == ("messenger", "PSID-123")


@pytest.mark.parametrize(
    "canal, error",
    [
        ("whatsapp", 'Meta respondió 400: {"error":{"code":131047,"message":"Re-engagement message"}}'),
        ("messenger", 'Meta respondió 400: {"error":{"code":10,"error_subcode":2018278}}'),
        ("instagram", 'Meta respondió 400: {"error":{"code":10,"error_subcode":2534022}}'),
    ],
)
def test_fuera_de_las_24_horas_se_explica_sin_jerga(api, session, canal, error):
    orden = _orden_de(api, session, canal)
    con_enviador(EnviadorQueRecuerda(error))
    r = avanzar(api, orden, "en_produccion").json()
    assert r["etapa_actual"] == "en_produccion"  # la orden avanza igual
    assert r["aviso_al_cliente"] == "no_enviado"
    assert "más de 24 horas" in r["detalle_aviso"] and "131047" not in r["detalle_aviso"]


def test_otros_errores_se_explican_sin_el_detalle_tecnico():
    texto = motivo_legible("whatsapp", 'Meta respondió 401: {"error":{"message":"token vencido"}}')
    assert texto.startswith("WhatsApp no aceptó el aviso (error 401)")
    assert "{" not in texto and "bitácora" in texto


def test_un_destinatario_que_meta_no_reconoce_se_explica():
    # Pasó en staging con un cliente archivado: Meta responde (#100) recipient[id] inválido.
    error = (
        'Meta respondió 400: {"error":{"message":"(#100) Param recipient[id] must be a valid ID '
        'string (e.g., \\"123\\")","type":"OAuthException","code":100}}'
    )
    texto = motivo_legible("messenger", error)
    assert texto.startswith("Messenger no reconoce la cuenta de este cliente")
    assert "OAuthException" not in texto


def test_si_meta_no_responde_se_dice_asi():
    assert "no respondió en este momento" in motivo_legible("instagram", "No se pudo contactar a Meta: timeout")


def test_el_detalle_tecnico_queda_en_la_bitacora(api, session, caplog):
    orden = _orden_de(api, session, "messenger")
    con_enviador(EnviadorQueRecuerda('Meta respondió 400: {"error":{"code":100,"message":"recipient"}}'))
    r = avanzar(api, orden, "en_produccion").json()
    assert r["aviso_al_cliente"] == "no_enviado" and "{" not in r["detalle_aviso"]
    assert any("recipient" in m for m in caplog.messages)
