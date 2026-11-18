# JOY-74 · Seguridad del agente II (RNF-01)

Fecha: 18-nov-2026 · Continúa JOY-70 (guardrails de entrada y salida).

## 1. Límite de mensajes por cliente

| Parámetro | Variable | Valor en staging |
|---|---|---|
| Mensajes permitidos por ventana | `AGENTE_LIMITE_MENSAJES` | 15 |
| Duración de la ventana (segundos) | `AGENTE_LIMITE_SEGUNDOS` | 60 |

- Se cuenta por cliente y por canal en Redis (`limite:<canal>:<id>`); la clave vence sola al
  terminar la ventana.
- El primer mensaje que se pasa del límite recibe un aviso fijo y queda registrado; los
  siguientes de la misma ventana no se responden. En ningún caso se llama al modelo ni al
  clasificador.
- Todos los mensajes del cliente se guardan igual en su conversación (el asesor los ve).
- Si la conversación está en manos de un asesor, no se limita (el agente no responde).
- Si Redis falla, no se bloquea a nadie (se registra una advertencia en la bitácora).

## 2. Registro de intentos bloqueados

Tabla `intentos_bloqueados`: fecha, cliente, canal, motivo, regla y el id del mensaje. **No
copia el texto del cliente**: apunta al mensaje de la conversación, así el dato personal queda
en un solo lugar (RNF-09).

| Motivo | Cuándo | Reglas |
|---|---|---|
| `instrucciones` | Guardrail de entrada: el mensaje intenta manipular al agente | `cambiar_instrucciones`, `pedir_prompt`, `modo_sin_restricciones`, `cambiar_identidad` |
| `limite_de_mensajes` | El cliente se pasó del límite (una vez por ventana) | — |
| `respuesta_corregida` | Guardrail de salida corrigió la respuesta del modelo | `instrucciones_en_respuesta`, `dato_no_autorizado` |

Consulta: `GET /seguridad/intentos?dias=30&motivo=…` (rol dirección o admin). El Resumen del
panel muestra el total del periodo por motivo.

Mejoras hechas al revisar:
- El guardrail de entrada ahora se aplica antes de cualquier modelo, también cuando responde
  el motor de reglas (antes solo protegía el camino de LangChain).
- El guardrail de salida va antes de revisar los enlaces: un correo inventado como
  `juan@correo.com` se tomaba por enlace y quedaba a medias en la respuesta.

## 3. Pruebas automáticas

`02_codigo_fuente/backend/tests/test_seguridad_agente_ii.py` (20 pruebas): límite, aviso único,
vencimiento de la ventana, límite por cliente y canal, Redis caído, configuración inválida,
conversación escalada, registro por regla, registro sin texto del cliente, motor de reglas
protegido, respuestas corregidas, consulta por rol y métricas.

## 4. Revisión de dependencias del frontend (`npm audit`)

| Paquete | Severidad | Dónde se usa | Acción |
|---|---|---|---|
| zod < 4.6.6 | alta | Solo desarrollo (eslint-plugin-react-hooks) | Actualizado a 4.6.7 |
| minimatch 7.0.0–11.0.0 | moderada | Solo desarrollo (eslint) | Actualizado a 11.0.9 (eslint 10.15.0) |

- `npm audit --omit=dev` (lo que llega al navegador): 0 vulnerabilidades antes y después.
- Después de `npm audit fix` (sin `--force`): 0 vulnerabilidades en total; lint y build sin
  cambios.

## 5. Número de WhatsApp de contacto

`JOYERIA_WHATSAPP` se limpia y queda solo con dígitos (guiones, espacios, `+` y paréntesis se
quitan). Con guiones, `wa.me` tomaba el número como nombre de usuario y no abría el chat.
