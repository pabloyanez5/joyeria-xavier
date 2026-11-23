# JOY-75 · Casos de prueba del cotizador (RNF-07)

Fecha: 23-nov-2026 · Requisito: el cotizador calcula bien en el 100 % de al menos 20 casos.

## Regla de cálculo

**Precio = peso (g) × precio del gramo del material + mano de obra**, redondeado a centavos
(mitad hacia arriba: 0,505 → 0,51).

- El precio del gramo es la tarifa vigente más reciente del material y quilataje (las tarifas
  con fecha futura no cuentan). Material y quilataje se comparan sin importar mayúsculas.
- **Precio de tabla (respaldo):** si la pieza no tiene peso válido, no hay tarifa vigente con
  precio del gramo válido o la mano de obra es negativa, se usa el precio fijo de la tabla
  `precios`.
- **No se cotiza:** si tampoco el precio de tabla es válido (cero o negativo), o la pieza no se
  ofrece en ese material/quilataje. La web y el agente derivan al cliente a un asesor.
- Valores no válidos: peso ≤ 0, precio del gramo ≤ 0, mano de obra < 0, precio de tabla ≤ 0.
  Sin mano de obra registrada cuenta como 0.

## Casos

Montos en USD. «Resultado esperado» indica el precio y con qué se calculó: fórmula (peso ×
gramo + mano de obra) o tabla (precio fijo de respaldo).

| ID | Caso | Material | Peso (g) | USD por gramo | Mano de obra | Precio de tabla | Resultado esperado |
|---|---|---|---|---|---|---|---|
| C01 | Anillo solitario en oro 18k | oro 18k | 4,00 | 95,00 | 78,00 | 450,00 | 458,00 (fórmula) |
| C02 | Anillo solitario en oro 14k | oro 14k | 4,00 | 74,00 | 78,00 | 360,00 | 374,00 (fórmula) |
| C03 | Anillo solitario en plata | plata | 4,00 | 1,60 | 78,00 | 85,00 | 84,40 (fórmula) |
| C04 | Anillo con halo en oro 18k | oro 18k | 6,00 | 95,00 | 210,00 | 780,00 | 780,00 (fórmula) |
| C05 | Anillo sello en plata | plata | 3,50 | 1,60 | 62,00 | 70,00 | 67,60 (fórmula) |
| C06 | Argolla clásica en oro 14k | oro 14k | 3,00 | 74,00 | 35,00 | 260,00 | 257,00 (fórmula) |
| C07 | Argolla diamantada en oro 18k | oro 18k | 3,20 | 95,00 | 56,00 | 360,00 | 360,00 (fórmula) |
| C08 | Cadena cubana en oro 18k | oro 18k | 9,00 | 95,00 | 125,00 | 980,00 | 980,00 (fórmula) |
| C09 | Cadena veneciana en plata | plata | 2,80 | 1,60 | 50,00 | 55,00 | 54,48 (fórmula) |
| C10 | Pulsera esclava en oro 14k | oro 14k | 4,20 | 74,00 | 21,00 | 340,00 | 331,80 (fórmula) |
| C11 | Aretes con perla en oro 14k | oro 14k | 1,80 | 74,00 | 89,00 | 210,00 | 222,20 (fórmula) |
| C12 | Dije corazón en oro 18k | oro 18k | 1,20 | 95,00 | 36,00 | 150,00 | 150,00 (fórmula) |
| C13 | Redondeo hacia arriba (117,5265) | oro 18k | 1,23 | 95,55 | 10,00 | 1,00 | 127,53 (fórmula) |
| C14 | Redondeo hacia abajo (82,2843) | oro 14k | 1,11 | 74,13 | 5,00 | 1,00 | 87,28 (fórmula) |
| C15 | Medio centavo exacto (0,505) sube | plata | 0,50 | 1,01 | 20,00 | 1,00 | 20,51 (fórmula) |
| C16 | Sin mano de obra registrada (cuenta 0) | oro 18k | 2,00 | 95,00 | — | 1,00 | 190,00 (fórmula) |
| C17 | Pieza pesada (125,5 g) | oro 18k | 125,50 | 95,00 | 300,00 | 1,00 | 12222,50 (fórmula) |
| C18 | Material y quilataje escritos distinto (ORO 18K) | oro 18k (pide «Oro 18K») | 4,00 | 95,00 | 78,00 | 450,00 | 458,00 (fórmula) |
| C19 | Material sin tarifa vigente | plata | 4,00 | sin tarifa | 78,00 | 85,00 | 85,00 (tabla) |
| C20 | Pieza sin peso registrado | oro 18k | — | 95,00 | 78,00 | 450,00 | 450,00 (tabla) |
| C21 | Peso cero | oro 18k | 0,00 | 95,00 | 78,00 | 450,00 | 450,00 (tabla) |
| C22 | Peso negativo | oro 18k | -4,00 | 95,00 | 78,00 | 450,00 | 450,00 (tabla) |
| C23 | Precio del gramo en cero | oro 18k | 4,00 | 0,00 | 78,00 | 450,00 | 450,00 (tabla) |
| C24 | Mano de obra negativa | oro 18k | 4,00 | 95,00 | -10,00 | 450,00 | 450,00 (tabla) |
| C25 | Peso cero y sin precio de tabla válido | oro 18k | 0,00 | 95,00 | 78,00 | 0,00 | no se cotiza |
| C26 | Combinación que la pieza no ofrece (pide 14k) | oro 18k (pide «oro 14k») | 4,00 | 74,00 | 78,00 | 450,00 | no se cotiza |

C01–C12 usan las piezas, pesos y tarifas de demostración del catálogo de la joyería.

## Cómo se prueba

- Prueba automática: `02_codigo_fuente/backend/tests/test_cotizador_casos.py`. Cada caso crea
  su pieza, su precio de tabla y su tarifa, y cotiza por la API (`GET
  /productos/{id}/cotizacion`), igual que la web y el agente.
- Además de la cifra, cada caso revisa que el precio venga en centavos y que el desglose
  (material + mano de obra) sume exactamente el precio.
- Pruebas complementarias: la tarifa más reciente es la que cuenta (ni la vieja ni la futura),
  y una combinación sin precio válido no aparece en el catálogo.
- La prueba `test_el_documento_tiene_los_mismos_casos` compara esta tabla con la del código:
  si alguien cambia un caso en un lado y no en el otro, falla.

## Resultado

26 de 26 casos pasan (100 %). Se corre en cada Pull Request (GitHub Actions).

## Cambio en el código a raíz de estas pruebas

Antes, una pieza con peso cero o negativo se cotizaba igual con la fórmula: en oro podía salir
solo la mano de obra, o incluso un precio negativo. Ahora esos valores no se usan: se toma el
precio de tabla y, si tampoco es válido, la combinación no se ofrece y la atiende un asesor.

