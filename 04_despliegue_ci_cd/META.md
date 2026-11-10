# Conexión con WhatsApp (Meta Business API)

El backend recibe los mensajes en `POST /webhook/meta`, deja que el agente los atienda y responde al cliente
llamando a la API de Meta (`app/meta_envio.py`). Hoy el envío cubre WhatsApp; Instagram y Messenger solo reciben.

## Variables (en el `.env` del servidor, nunca en el repositorio)

| Variable | De dónde sale |
|---|---|
| `META_VERIFY_TOKEN` | Un texto que tú eliges; el mismo que escribes al registrar el webhook en Meta |
| `META_APP_SECRET` | Meta for Developers → tu app → Configuración → Básica → Clave secreta. Si está definida, el webhook rechaza (403) los mensajes sin firma válida |
| `META_ACCESS_TOKEN` | WhatsApp → API Setup (el temporal dura 24 h; el permanente sale de un usuario del sistema) |
| `META_PHONE_NUMBER_ID` | WhatsApp → API Setup → "Phone number ID" |
| `META_API_VERSION` | La versión que muestra Meta en el cURL de ejemplo (por defecto `v23.0`) |

## Registro del webhook en Meta

1. La URL pública debe ser HTTPS: `https://<dominio-o-túnel>/api/webhook/meta`.
2. Token de verificación: el valor de `META_VERIFY_TOKEN`.
3. Suscribir el campo `messages`.

## Comprobaciones

- `GET https://<url>/api/webhook/meta?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=123` debe responder `123`.
- Al escribir al número de prueba, el registro del backend muestra "Respuesta del agente" y llega la respuesta a WhatsApp.
- Si Meta rechaza el envío, el registro muestra "No se pudo enviar la respuesta" con el motivo y el webhook igual responde 200.
