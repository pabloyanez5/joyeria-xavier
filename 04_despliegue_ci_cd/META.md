# Conexión con WhatsApp (Meta Business API)

El backend recibe los mensajes en `POST /webhook/meta`, deja que el agente los atienda y responde al cliente
llamando a la API de Meta (`app/meta_envio.py`). El envío cubre WhatsApp, Messenger (JOY-65) e Instagram (JOY-73):
Messenger e Instagram se envían por la página de Facebook, con fotos y respuestas rápidas.

## Variables (en el `.env` del servidor, nunca en el repositorio)

| Variable | De dónde sale |
|---|---|
| `META_VERIFY_TOKEN` | Un texto que tú eliges; el mismo que escribes al registrar el webhook en Meta |
| `META_APP_SECRET` | Meta for Developers → tu app → Configuración → Básica → Clave secreta. Si está definida, el webhook rechaza (403) los mensajes sin firma válida |
| `META_ACCESS_TOKEN` | WhatsApp → API Setup (el temporal dura 24 h; el permanente sale de un usuario del sistema) |
| `META_PHONE_NUMBER_ID` | WhatsApp → API Setup → "Phone number ID" |
| `META_API_VERSION` | La versión que muestra Meta en el cURL de ejemplo (por defecto `v23.0`) |
| `META_PAGE_ID` | El ID de la página de Facebook (Messenger e Instagram se envían por ella) |
| `META_PAGE_ACCESS_TOKEN` | Token de la página, sacado con el token del usuario del sistema (ver Instagram más abajo) |
| `META_INSTAGRAM_APP_SECRET` | Opcional. Solo si Instagram firma con la clave de su propia app (inicio de sesión de Instagram); el webhook acepta cualquiera de las dos claves |

## Registro del webhook en Meta

1. La URL pública debe ser HTTPS: `https://<dominio-o-túnel>/api/webhook/meta`.
2. Token de verificación: el valor de `META_VERIFY_TOKEN`.
3. Suscribir el campo `messages`.

## Comprobaciones

- `GET https://<url>/api/webhook/meta?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=123` debe responder `123`.
- Al escribir al número de prueba, el registro del backend muestra "Respuesta del agente" y llega la respuesta a WhatsApp.
- Si Meta rechaza el envío, el registro muestra "No se pudo enviar la respuesta" con el motivo y el webhook igual responde 200.

## Instagram (JOY-73)

La cuenta profesional de Instagram (de prueba: `joyeriaxavier.test`) debe estar vinculada a la página
de Facebook. Pasos, en este orden:

1. **Portfolio comercial → Usuarios del sistema → bot-joyeria → Activos asignados**: dar a la cuenta de
   Instagram «Acceso total» (incluye los mensajes).
2. **App de Instagram (cuenta de la joyería) → Configuración → Mensajes y respuestas a historias →
   Herramientas conectadas**: activar «Permitir acceso a los mensajes».
3. **Meta for Developers → caso de uso «API de Instagram» → API setup with Unified login → 3. Configurar
   webhooks**: la misma URL y el mismo token de verificación que WhatsApp y Messenger; suscribir los
   campos `messages` y `messaging_postbacks`. No hace falta la «URL de redireccionamiento» de la sección 1
   (es para el inicio de sesión con Instagram, que no se usa).
4. **Token**: en el usuario del sistema, «Generar token» con `pages_messaging`, `pages_manage_metadata`,
   `pages_show_list`, `pages_read_engagement`, `instagram_basic` e `instagram_manage_messages`. Con ese
   token, en el Explorador de la API Graph: `GET <META_PAGE_ID>?fields=access_token,instagram_business_account`.
   El `access_token` de la respuesta va en `META_PAGE_ACCESS_TOKEN`; `instagram_business_account` confirma
   que Instagram está vinculado.
5. En el `.env`: `JOYERIA_INSTAGRAM=<usuario de la cuenta>` (el enlace «Escríbenos por Instagram» de la web)
   y luego `docker compose -f docker-compose.staging.yml up -d api`.

Mientras la app esté en modo desarrollo, Meta solo entrega mensajes de cuentas con un rol en la app
(administrador, desarrollador o evaluador de Instagram).

Comprobación: escribir un DM a la cuenta y revisar
`docker compose -f docker-compose.staging.yml logs --since 5m api | grep -i instagram`; debe aparecer
«Respuesta del agente a instagram ***xxxx».
