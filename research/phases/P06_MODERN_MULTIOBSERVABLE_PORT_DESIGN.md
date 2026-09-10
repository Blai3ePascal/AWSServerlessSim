# P06 — port seguro de multiobservable al Trellis moderno

## Objetivo

Pasar la semántica conjunta de P05 al Trellis moderno congelado en `024db1d3b5b038f565c476dd1b51885271f7b0bf` sin romper ni sustituir el kernel rápido actual de un observable.

## Lo que hay ahora en el moderno

El código moderno todavía conserva `uint64_t obs_mask` al parsear fallos y en `TesseractTrellisWideLayerTemplate`. La pérdida de generalidad ocurre después:

- el constructor rechaza `num_observables > 1`;
- al compilar capas, `obs_mask` se reduce a `bool toggles_observable`;
- cada estado guarda únicamente `mass0` y `mass1`;
- si un fallo lógico está presente, esas dos masas se intercambian;
- al final sólo se decide entre máscara 0 y máscara 1.

Esto es un kernel binario muy optimizado. No lo convertimos a la fuerza en un mapa de 64 bits porque sería mezclar una optimización ya probada con nuestro experimento y luego no sabríamos qué hemos roto.

## Diseño P06a

### Camino A: 0 o 1 observable

Se mantiene el kernel compilado actual. Para estos casos queremos conservar el comportamiento moderno existente.

### Camino B: 2..64 observables

Se añade un camino experimental separado. Cada entrada conserva:

- el estado de detectores;
- un `uint64_t obs_mask` completo;
- la masa de probabilidad asociada.

La expansión combina observables mediante XOR. Las explicaciones con el mismo síndrome pero distinta máscara lógica no se confunden entre sí. Al final se elige la máscara lógica completa con mayor masa: joint-MAP.

## Primera versión deliberadamente conservadora

P06a prioriza **corrección**, no velocidad. La ruta multiobservable inicial sólo admite `TesseractTrellisRankingMode::MassOnly` y `beam_eps == 0`. Si se pide un modo que todavía no hemos validado, se rechaza explícitamente en lugar de fingir que funciona.

Los modos con future detcost y otros ajustes se incorporarán después de cerrar la corrección de esta ruta básica.

## El primer run rojo y por qué NO era un fallo del decoder

El primer workflow P06 fue el run `34454002499`. El resultado real fue:

- la copia moderna upstream sin tocar pasó su suite original completa;
- la referencia P05 se reconstruyó desde cero y pasó 12/12 pruebas;
- el parche P06 se aplicó y compiló correctamente;
- las 7/7 pruebas nuevas de P06 pasaron, incluido el pequeño oráculo exacto para todos los síndromes usados;
- de las 7 pruebas antiguas ejecutadas sobre la copia modificada, 6 pasaron y sólo falló `TesseractTrellisDecoderTest.RejectsMoreThanOneObservable`.

Ese último fallo era inevitable por diseño: la prueba antigua exige que construir Trellis con más de un observable lance una excepción, mientras P06 existe precisamente para permitirlo. El CI estaba pidiendo simultáneamente dos cosas incompatibles.

Por tanto, el rojo del run `34454002499` se clasifica como **fallo del contrato del arnés de CI**, no como evidencia de fallo de corrección del kernel multiobservable.

## Cómo tratamos esa prueba antigua sin hacer trampas

No borramos silenciosamente la prueba ni dejamos de comprobar upstream.

1. La copia moderna **intocable** sigue ejecutando la suite upstream original completa. Allí `RejectsMoreThanOneObservable` debe seguir pasando, porque ése es el comportamiento real del SHA congelado.
2. Sobre la copia **modificada**, el arnés localiza exactamente esa prueba y sustituye únicamente su expectativa por `AllowsMultipleObservablesInExperimentalMassOnlyPath`.
3. Las otras seis expectativas upstream permanecen sin cambiar y deben seguir pasando.
4. La nueva capacidad queda cubierta además por una suite P06 específica mucho más fuerte que la antigua prueba de rechazo.

El cambio de contrato se aplica con `scripts/instrument/apply_p06_expected_upstream_contract.py` y queda registrado en `p06-upstream-contract-report.json` dentro del artefacto de evidencias.

## Contrato de corrección P06a

Para considerar P06a verde deben cumplirse todas estas condiciones:

1. El SHA moderno congelado es exactamente `024db1d3b5b038f565c476dd1b51885271f7b0bf`.
2. La copia upstream sin modificar pasa todos sus tests originales.
3. P05 se reconstruye desde el ancestro público `56996facf54c25e6c08fed19d8902f40e1971f55` y sus 12 pruebas pasan.
4. El parche P06 aplica sin errores y `git diff --check` queda limpio.
5. El Trellis moderno modificado compila.
6. Las seis regresiones upstream no relacionadas con la antigua prohibición de multiobservable siguen pasando.
7. La expectativa antigua de rechazo se sustituye explícitamente por una expectativa positiva de soporte multiobservable MassOnly.
8. Las 7 pruebas P06 pasan: máscara conjunta, cancelación XOR, joint-MAP frente a bits independientes, observable 63, rechazo de 64, rechazo de rankings no validados y comparación con un enumerador exacto pequeño.
9. GitHub Actions no se usa como benchmark científico.

## Qué hemos probado y qué todavía NO

P06a demuestra corrección sobre los casos exactos y de regresión incluidos en el arnés. Todavía **no** demuestra:

- equivalencia con ninguna rama privada de Google;
- rendimiento científico ni aceleración medida en GitHub Actions;
- soporte multiobservable para los modos future-detcost;
- soporte multiobservable con `beam_eps != 0`;
- comportamiento de producción sobre BB grandes;
- que esta primera implementación sea la más rápida posible.

## Siguiente paso si P06a queda verde

Con la corrección básica cerrada, el siguiente paso razonable es aumentar el diferencial entre la referencia P05 y el moderno P06 sobre un corpus reproducible de DEM pequeños y después empezar a medir escalabilidad en entornos controlados. Sólo entonces tiene sentido optimizar la estructura de estados o incorporar los modos de ranking modernos.