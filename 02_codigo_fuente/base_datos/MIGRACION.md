# Migración de datos de prueba (JOY-48)

Herramienta para cargar clientes y órdenes desde archivos CSV y para dejar la base de datos lista para la demostración.

## Uso rápido

Desde `02_codigo_fuente/backend` (con el entorno virtual activo y Postgres arriba):

```
python -m app.migracion --demo
```

Carga el catálogo (12 productos) y los datos ficticios de `app/datos_demo/` (12 clientes y 18 órdenes en distintas etapas; 3 quedan `en_cola` con acuse pendiente y aparecen en la cola del panel).

En staging:

```
docker compose -f docker-compose.staging.yml exec api python -m app.migracion --demo
```

## Importar archivos propios

```
python -m app.migracion --clientes clientes.csv --ordenes ordenes.csv
```

Se puede pasar solo uno de los dos. Si se importan órdenes, los clientes deben existir antes (en la base o en el `--clientes` del mismo comando).

### clientes.csv

| Columna | Obligatoria | Detalle |
|---|---|---|
| canal | sí | `whatsapp`, `instagram` o `messenger` |
| id_canal | sí | Identificador del cliente en ese canal (teléfono, usuario, PSID) |
| nombre | sí | Nombre del perfil (máx. 200 caracteres) |
| talla | no | Máx. 20 caracteres |

Un cliente se identifica por `canal + id_canal`; si ya existe se omite.

### ordenes.csv

| Columna | Obligatoria | Detalle |
|---|---|---|
| canal, id_canal | sí | Identifican al cliente (debe existir) |
| producto | no | Nombre exacto del catálogo; vacío si es un trabajo a medida o reparación |
| descripcion | sí | Entre 3 y 1000 caracteres |
| etapa | sí | `en_cola`, `en_produccion`, `terminada` o `entregada` |
| fecha | sí | `AAAA-MM-DD` |

Reglas: la orden se crea con esa fecha; `acuse_pendiente` es verdadero solo si la etapa es `en_cola`; se registra la etapa en el historial. Una orden se considera repetida si coincide cliente + descripción + fecha.

## Comportamiento

- Acepta separador `,` o `;` y archivos guardados desde Excel (UTF-8 con BOM).
- Cada fila se valida por separado: una fila con error se informa con su número (el encabezado es la fila 1) y el resto se carga.
- Es idempotente: ejecutarlo dos veces no duplica datos.
- Código de salida: `0` sin errores, `1` si hubo filas con error, `2` si el archivo no se pudo leer o le faltan columnas.

## Ejemplo de salida

```
Catálogo: 12 productos nuevos
Clientes: 12 importadas, 0 omitidas (ya existían), 0 con error
Órdenes: 18 importadas, 0 omitidas (ya existían), 0 con error
```

Todos los datos de `app/datos_demo/` son ficticios.
