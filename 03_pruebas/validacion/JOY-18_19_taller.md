# Validación de JOY-18 (US-10) y JOY-19 (US-11) · Taller

Fecha: 23-nov-2026 · Dependen de JOY-78 (usuarios y roles).

Prueba automática: `02_codigo_fuente/backend/tests/test_taller_acuse_y_entrega.py` (12 pruebas),
más las de etapas, acceso y cambios que ya existían (`test_etapas.py`, `test_acceso.py`,
`test_cancelar_modificar.py`).

## JOY-18 · US-10: el taller ve sus órdenes y confirma el acuse

> Como equipo de taller, quiero visualizar las órdenes asignadas y confirmar el acuse de recibo
> desde el panel administrativo.
> **Criterio:** taller confirma acuse; orden pasa a «en producción» con marca de tiempo y usuario
> responsable. El acuse guarda el usuario de taller y la hora.

| # | Criterio | Cómo se cumple | Prueba | Estado |
|---|---|---|---|---|
| 1 | El taller ve las órdenes que le llegan | Cola del taller (`GET /ordenes/cola`) y tablero con la columna «En cola», la más antigua primero, con la etiqueta «Acuse pendiente». Solo entran órdenes con el abono verificado. | `test_el_taller_ve_las_ordenes_que_le_llegan` | ✅ |
| 2 | Confirma el acuse desde el panel | Botón «Recibir y pasar a producción» en la tarjeta y «Confirmar recibo y pasar a producción» en el detalle. | Recorrido en el panel (captura) | ✅ |
| 3 | La orden pasa a «en producción» | Confirmar el acuse en la cola mueve la orden a producción, con su paso en el historial y el aviso al cliente por su canal (se puede no avisar). | `test_confirmar_el_acuse_pasa_la_orden_a_produccion_con_responsable_y_hora`, `test_el_acuse_se_puede_confirmar_sin_avisar_al_cliente` | ✅ (cambio) |
| 4 | Marca de tiempo y usuario responsable | `acuse_por` / `acuse_en` en la orden y el paso «En producción» del historial con usuario y hora. El detalle muestra «Recibida por … · fecha y hora». | Misma prueba del #3 | ✅ |
| 5 | Solo el taller confirma | El asesor y dirección reciben 403. | `test_solo_el_taller_confirma_el_acuse` | ✅ |

Casos adicionales: si el asesor modifica una orden que ya está en producción, el taller vuelve a
confirmar («Confirmar que vi el cambio») sin que la orden salte de etapa
(`test_si_el_asesor_cambio_la_orden_en_produccion_el_acuse_solo_confirma_que_la_vio`);
confirmar dos veces no duplica nada (`test_confirmar_dos_veces_no_cambia_nada`).

**Cambio hecho al validar:** antes, «Confirmar recibo» solo marcaba el acuse y la orden seguía en
la cola; el taller tenía que tocar además «Pasar a en producción». Ahora es un solo paso, como dice
el criterio.

## JOY-19 · US-11: el taller actualiza la etapa productiva

> Como equipo de taller, quiero actualizar la etapa productiva de cada orden conforme avanza la
> fabricación.
> **Criterio:** transición de etapa registrada con marca de tiempo; historial completo visible.
> Cada transición guarda responsable y hora; se añade el registro de la entrega física (fecha y
> quién entrega).

| # | Criterio | Cómo se cumple | Prueba | Estado |
|---|---|---|---|---|
| 1 | El taller actualiza la etapa | En cola → En producción → Terminada → Entregada, de una en una (no se saltan ni se retroceden etapas desde el taller). El cliente recibe un aviso por su canal en cada paso. | `test_el_taller_avanza_etapa_por_etapa_hasta_la_entrega`, `test_no_se_puede_saltar_ni_retroceder_etapas` | ✅ |
| 2 | Cada transición con responsable y hora | Tabla `historial_etapas`: etapa, usuario y fecha/hora de cada paso. | `test_cada_transicion_queda_con_responsable_y_hora_y_el_historial_es_completo` | ✅ |
| 3 | Historial completo visible | Sección «Historial» en el detalle de la orden: todas las etapas en orden, con fecha, hora y usuario; también modificaciones, retrocesos y cancelaciones con su motivo (JOY-23). | Misma prueba del #2 y recorrido en el panel | ✅ |
| 4 | Registro de la entrega física: fecha y quién entrega | Al registrar «Entregada» se guarda quién la entregó (`entregada_por`) y cuándo (`entregada_en`). El detalle muestra «Entregada por … · fecha y hora». Opcional: quién retira la joya si no es el titular, que queda en el historial («Retiró: …»). | `test_la_entrega_fisica_guarda_quien_la_entrego_cuando_y_quien_retiro`, `test_la_entrega_sin_nota_no_inventa_quien_retiro` | ✅ (nuevo) |
| 5 | Roles | La entrega física la registra el taller o el asesor (quien atiende al cliente en la joyería); el asesor no puede avanzar las demás etapas. | `test_el_asesor_solo_registra_la_entrega` | ✅ (nuevo) |

**Cambio hecho al validar:** la orden guarda los datos de la entrega física (migración
`c3f8a2d6e4b1`); las órdenes ya entregadas toman la fecha y el usuario de su paso «Entregada» del
historial.

## Resultado

JOY-18: 5 de 5 criterios cumplidos. JOY-19: 5 de 5 criterios cumplidos. Todas las pruebas pasan en
CI. Evidencia visual en `05_evidencias/sprint4/` (detalle de una orden en cola con el botón de
acuse y una orden entregada con su registro de entrega).
