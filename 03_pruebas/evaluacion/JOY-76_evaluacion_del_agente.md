# JOY-76 · Evaluación del agente con el modelo en 50 casos (RNF-07)

Fecha: 24-nov-2026 · Modelo principal: `gemini-3.1-flash-lite` (respaldo `gemini-2.5-flash`) ·
Entorno: staging (VPS).

**Resultado: el agente real eligió la acción correcta en el 96 % de los casos (48 de 50).** RNF-07
pide al menos 85 % en al menos 50 interacciones: ✅ cumplido.

## 1. Qué se midió

Los 50 mensajes de `app/agente/casos_evaluacion.py` (los mismos de JOY-15): saludo 6, cotizar 9,
catálogo 8, estado del pedido 8, asesor 8, despedida 5 y otros 6.

1. **Clasificador de intenciones** (`python -m app.agente.evaluar`): la etiqueta que da el
   clasificador con reglas y con el modelo.
2. **Agente real** (`python -m app.agente.evaluar --agente`, nuevo en JOY-76): cada mensaje pasa
   por el agente completo de LangChain con sus herramientas, en una conversación nueva y con un
   cliente que tiene una orden en producción. Se revisa si tomó la acción correcta:

| Intención del caso | Acción correcta del agente |
|---|---|
| saludo, despedida | conversar (sin herramientas) |
| cotizar, catálogo | herramienta del catálogo (o la lista de opciones) |
| estado del pedido | consultar su orden |
| asesor | derivar a un asesor |
| otro (horario, ubicación, pagos, fuera de tema) | conversar, informar o derivar; nunca inventar con el catálogo ni con una orden |

La evaluación del agente corre sobre una base temporal en memoria con el catálogo de prueba: no
crea clientes ni conversaciones en staging.

## 2. Primera ronda (antes de los ajustes)

| Medición | Resultado |
|---|---|
| Clasificador con reglas | 92 % (46/50) |
| Clasificador con el modelo | **94 % (47/50)** (8 de 50 llamadas cayeron a reglas por cuota 429 o tiempo de espera) |
| Agente real | 58 % (29/50) en total; **94 % (29/31) de los que respondió el modelo**. Los otros 19 fueron error 429 (cuota por minuto del plan gratuito de Gemini, con 2 s de pausa entre mensajes) |

Hallazgo importante: en «Quiero cotizar unas argollas de matrimonio» y «necesito un presupuesto
para unos aretes», el modelo **no consultó el catálogo e inventó precios** («desde los $150» cuando
lo real es $257; «desde $45» cuando lo real es $41,20).

## 3. Ajustes

1. **Precios verificados** (`seguridad.precios_sin_respaldo`): todo monto que escriba el modelo debe
   aparecer en lo que devolvieron las herramientas (catálogo, órdenes) o en lo que dijo el cliente
   (su presupuesto); se tolera el redondeo a dólares enteros. Si no, se le pide una vez que consulte
   el catálogo; si insiste, se responde con el enlace del catálogo real y queda registrado
   (`precio_no_verificado`). Pruebas: `tests/test_precios_verificados.py`.
2. **Reglas** (lo que responde si el modelo no está disponible): «¿cuánto me saldría…?», «cuánto
   tendría que pagar», «regalo» y «¿mi anillo ya está?». Con las reglas el set queda en 100 %
   (50/50); como se ajustaron sobre el mismo set, ese número es optimista, y por eso se agregaron 6
   frases nuevas que tampoco fallan (`tests/test_intenciones.py`).
3. **Clasificador**: «Saludos, ¿hay alguien por ahí?» es un saludo, no un pedido de asesor.
4. **Pausa de la medición**: 10 s entre mensajes para no chocar con la cuota del plan gratuito.

## 4. Segunda ronda: agente real

Acción correcta: **96 % (48/50)** · Respondió el modelo en los 50 casos (ninguno cayó a reglas ni
dio error) · Tiempo por mensaje: promedio 6,44 s, máximo 24,72 s.

Durante la ronda, el control de precios actuó 2 veces (el modelo volvió a escribir precios sin
consultar el catálogo y los corrigió con la herramienta: casos 8 y 10, ahora correctos) y el
reintento ante modelo saturado (JOY-94) actuó 2 veces (un 503 y un 504) sin pasar al respaldo. Esos
reintentos y segundas rondas explican los tiempos más altos; el promedio incluye la llamada a la
herramienta y la redacción de la respuesta.

| # | Mensaje | Esperada | Acción del agente | Origen | Resultado |
|---|---|---|---|---|---|
| 1 | Hola | saludo | conversar | modelo | ✅ |
| 2 | Buenos días | saludo | conversar | modelo | ✅ |
| 3 | buenas tardes, ¿cómo están? | saludo | conversar | modelo | ✅ |
| 4 | Hola buenas noches | saludo | conversar | modelo | ✅ |
| 5 | hey, qué tal | saludo | conversar | modelo | ✅ |
| 6 | Saludos, ¿hay alguien por ahí? | saludo | conversar | modelo | ✅ |
| 7 | ¿Cuánto cuesta un anillo de oro 18k? | cotizar | catalogo | modelo | ✅ |
| 8 | Quiero cotizar unas argollas de matrimonio | cotizar | catalogo | modelo | ✅ |
| 9 | me pueden dar el precio de una cadena cubana | cotizar | catalogo | modelo | ✅ |
| 10 | hola, necesito un presupuesto para unos aretes | cotizar | catalogo | modelo | ✅ |
| 11 | cuanto vale el anillo solitario en plata | cotizar | catalogo | modelo | ✅ |
| 12 | Quisiera saber el costo de un dije de corazón | cotizar | catalogo | modelo | ✅ |
| 13 | ¿cuánto me saldría una pulsera tejida en oro? | cotizar | catalogo | modelo | ✅ |
| 14 | precio de las argollas? | cotizar | catalogo | modelo | ✅ |
| 15 | Quisiera saber cuánto tendría que pagar por unas argollas | cotizar | catalogo | modelo | ✅ |
| 16 | ¿Qué modelos de anillos tienen? | catalogo | catalogo | modelo | ✅ |
| 17 | Me gustaría ver el catálogo | catalogo | catalogo | modelo | ✅ |
| 18 | muéstrame las cadenas que venden | catalogo | catalogo | modelo | ✅ |
| 19 | ¿tienen pulseras de plata? | catalogo | catalogo | modelo | ✅ |
| 20 | que diseños de aretes manejan | catalogo | catalogo | modelo | ✅ |
| 21 | quiero ver sus joyas | catalogo | catalogo | modelo | ✅ |
| 22 | Tienen fotos de las argollas? | catalogo | catalogo | modelo | ✅ |
| 23 | Estoy buscando un regalo para mi esposa | catalogo | conversar | modelo | ❌ |
| 24 | ¿Cómo va mi pedido? | estado_pedido | consultar_orden | modelo | ✅ |
| 25 | quería saber el estado de mi orden | estado_pedido | consultar_orden | modelo | ✅ |
| 26 | cuándo estará lista mi argolla | estado_pedido | consultar_orden | modelo | ✅ |
| 27 | ¿Mi anillo ya está? | estado_pedido | consultar_orden | modelo | ✅ |
| 28 | mi encargo ya llegó? | estado_pedido | consultar_orden | modelo | ✅ |
| 29 | ¿Puedo retirar hoy mi pedido? | estado_pedido | consultar_orden | modelo | ✅ |
| 30 | Hice una orden la semana pasada, ¿hay novedades? | estado_pedido | consultar_orden | modelo | ✅ |
| 31 | cuando me entregan mi cadena | estado_pedido | consultar_orden | modelo | ✅ |
| 32 | Quiero hablar con un asesor | asesor | asesor | modelo | ✅ |
| 33 | ¿Me puede comunicar con una persona? | asesor | asesor | modelo | ✅ |
| 34 | necesito atención de un humano | asesor | asesor | modelo | ✅ |
| 35 | Pásame con el vendedor, por favor | asesor | asesor | modelo | ✅ |
| 36 | quiero que me llamen para ver un diseño personalizado | asesor | asesor | modelo | ✅ |
| 37 | ¿Hay alguien que me pueda atender en persona? | asesor | conversar | modelo | ❌ |
| 38 | No me sirve el bot, quiero a alguien real | asesor | asesor | modelo | ✅ |
| 39 | Necesito hablar con la encargada | asesor | asesor | modelo | ✅ |
| 40 | Muchas gracias | despedida | conversar | modelo | ✅ |
| 41 | Gracias, hasta luego | despedida | conversar | modelo | ✅ |
| 42 | listo, eso es todo, adiós | despedida | conversar | modelo | ✅ |
| 43 | chao, buen día | despedida | conversar | modelo | ✅ |
| 44 | ok gracias por la ayuda | despedida | conversar | modelo | ✅ |
| 45 | ¿Cuál es el horario de atención? | otro | informacion | modelo | ✅ |
| 46 | ¿Dónde están ubicados? | otro | informacion | modelo | ✅ |
| 47 | ¿Aceptan tarjeta de crédito? | otro | informacion | modelo | ✅ |
| 48 | asdfgh | otro | conversar | modelo | ✅ |
| 49 | ¿Hacen reparaciones de relojes? | otro | conversar | modelo | ✅ |
| 50 | qué tiempo hace hoy | otro | conversar | modelo | ✅ |

### Casos fallidos

| # | Mensaje | Qué hizo | Análisis | Ajuste |
|---|---|---|---|---|
| 23 | «Estoy buscando un regalo para mi esposa» | Preguntó qué tipo de joya busca, sin abrir el catálogo | Coherente con sus instrucciones («una sola pregunta a la vez», primero el tipo de joya); el cliente no pidió ver nada aún | Ninguno: se considera aceptable |
| 37 | «¿Hay alguien que me pueda atender en persona?» | Le preguntó el motivo en vez de derivar | Error: pidió una persona | Instrucción nueva: si pregunta si hay alguien que lo atienda en persona o quiere una persona, derivar de inmediato sin preguntar el motivo |

El ajuste del caso 37 se hizo después de esta ronda; se verifica en la siguiente medición.

## 5. Observaciones

- **Plan gratuito de Gemini**: con varios mensajes por minuto aparece el error 429 (cuota). No es una
  falla del sistema: en ese caso responde el modelo de respaldo o el motor de reglas y el cliente
  igual recibe respuesta (se ve en el indicador «Respuestas con IA» del Resumen). Se elimina
  activando la facturación de Google AI Studio, sin cambiar código.
- La medición del agente es por acción (qué herramienta usó), no por la redacción de la respuesta;
  la calidad del texto la cubren las reglas de sus instrucciones y los guardrails de salida.

## 6. Cómo repetir la medición

En el servidor (en segundo plano, para que no la corte una desconexión de SSH):

```
cd /home/deploy/joyeria-xavier/04_despliegue_ci_cd && nohup docker compose -f docker-compose.staging.yml exec -T -e EVAL_PAUSA=10 api python -u -m app.agente.evaluar --agente > ~/evaluacion_agente.txt 2>&1 &
cat ~/evaluacion_agente.txt   # cuando termine (unos 10 min)
```
