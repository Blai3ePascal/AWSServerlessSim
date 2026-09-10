# Tesseract Trellis — extensión independiente para 0..64 observables

## Qué es esto

Esta rama contiene una reconstrucción **independiente y reproducible** de la capacidad multiobservable que necesitamos para Trellis. No contiene código privado de Google ni pretende ser una copia de una implementación privada inaccesible.

El objetivo funcional que sí cubre es el que necesitamos para experimentar con códigos que tienen más de un observable lógico:

- aceptar desde 0 hasta 64 observables lógicos (`L0`..`L63`);
- propagar la máscara lógica completa de 64 bits a través del Trellis;
- conservar conjuntamente estado de detectores + máscara de observables durante la acumulación de masa;
- seleccionar al final la **máscara lógica completa de máxima masa posterior (joint-MAP)**, no 64 decisiones independientes;
- devolver todos los índices lógicos predichos;
- mantener el comportamiento original de la ruta de 1 observable;
- soportar los modos de ranking actuales y `beam_eps`, no únicamente `MassOnly`;
- rechazar de forma explícita modelos con más de 64 observables.

## Por qué creemos que ésta es la semántica correcta

La reconstrucción no parte de una suposición arbitraria. En el historial público de `quantumlib/tesseract-decoder` existe una implementación anterior de Trellis que ya transportaba un `uint64_t obs_mask` junto al estado de detectores y hacía XOR de esa máscara al atravesar un fault. Esa implementación pública, sin embargo, terminaba reduciendo la decisión final a los casos `obs_mask == 0` y `obs_mask == 1`.

Nuestra extensión conserva esa representación pública y completa la decisión final para todas las máscaras posibles de hasta 64 observables. Después se porta esa semántica al Trellis moderno fijado en el SHA público indicado abajo.

Esto verifica la **capacidad funcional** que necesitamos. No demuestra identidad línea a línea, rendimiento equivalente ni equivalencia interna con ninguna rama privada que no hemos visto.

## Versiones fijadas

Upstream moderno:

```text
quantumlib/tesseract-decoder
024db1d3b5b038f565c476dd1b51885271f7b0bf
```

Referencia histórica pública usada para reconstruir la semántica multiobservable:

```text
56996facf54c25e6c08fed19d8902f40e1971f55
```

No usar `main` o `ftl` sin fijar un SHA si el objetivo es reproducir estos resultados.

## La prueba de una línea

Desde la raíz de este repositorio:

```bash
bash scripts/build_and_test_tesseract_multiobs64.sh
```

El script crea por defecto `.multiobs64-work/`, clona el upstream público, verifica el SHA, aplica la extensión, compila, ejecuta los tests y compara el decoder contra un oráculo probabilístico independiente.

Para usar otro directorio de trabajo:

```bash
bash scripts/build_and_test_tesseract_multiobs64.sh /tmp/tesseract-multiobs64
```

Requisitos:

- Linux;
- `git`;
- Python 3;
- Bazel/Bazelisk;
- compilador C++ compatible con el proyecto original;
- acceso a Internet únicamente para clonar dependencias públicas.

## Qué archivos cambian realmente en Tesseract

Los scripts de `scripts/instrument/` se aplican sobre una copia limpia del upstream. El resultado exacto se puede guardar como un único patch:

```text
tesseract-multiobservable64.patch
```

Secuencia de aplicación:

```bash
python3 scripts/instrument/apply_p06_modern_multiobs.py ...
python3 scripts/instrument/apply_p06_expected_upstream_contract.py ...
python3 scripts/instrument/apply_p06b_modern_multiobs_edge_tests.py ...
python3 scripts/instrument/apply_p07_complete_multiobs64_modes.py ...
python3 scripts/instrument/apply_p07b_mode_equivalence_tests.py ...
python3 scripts/instrument/apply_p07c_gtest_main_fix.py ...
python3 scripts/instrument/apply_p06c_diff_driver.py ...
```

`P07c` no cambia el decoder: corrige únicamente el enlace del ejecutable de tests añadiendo `@gtest//:gtest_main`, igual que los tests del upstream.

## Qué se ha añadido al decoder

La ruta original optimizada se conserva para 0/1 observable. Para 2..64 observables se utiliza una representación genérica en la que cada entrada del beam contiene:

```text
(detector_state, observable_mask, mass, ranking_penalty)
```

La expansión de un fault realiza:

```text
observable_mask_next = observable_mask_current XOR fault.observable_mask
```

Las entradas sólo se fusionan cuando coinciden **estado de detector y máscara lógica**. Para seleccionar qué estados sobreviven al beam, la masa se agrega por estado de detector, de modo que varias máscaras lógicas del mismo estado no consumen artificialmente varias posiciones del beam.

Al finalizar, para el estado detector válido se suma la masa por máscara lógica completa y se selecciona la máscara con mayor masa. Los empates exactos se resuelven escogiendo la máscara numéricamente menor para garantizar determinismo.

## Qué se prueba

### 1. Regresión del upstream

Se ejecuta el test original:

```bash
bazel test //src:tesseract_trellis_tests
```

La extensión no debe romper el comportamiento existente.

### 2. Casos multiobservable dirigidos

Se prueban explícitamente:

- 2 observables;
- 8 observables;
- 12 observables;
- bits altos;
- 64 observables con `L63`;
- rechazo de `L64` / 65 observables;
- reconstrucción de varios bits simultáneos;
- salida `decode()` con varios índices lógicos.

### 3. Modos del Trellis

Se prueba la ruta multiobservable con:

- `MassOnly`;
- `FutureDetcostRanked`;
- `FutureActiveDetcostRanked`;
- distintos `beam_width`;
- `beam_eps = 0` y poda por `beam_eps`.

Además se compara una versión detector-equivalente de 1 observable contra una que fuerza la nueva ruta de 2 observables para comprobar que ranking, poda y `low_confidence` se mantienen coherentes.

### 4. Oráculo exacto independiente

La prueba principal no compara sólo una versión de Tesseract contra otra.

Se generan **640 casos deterministas** con conteos de observables:

```text
2, 8, 12, 32 y 64
```

Incluyen explícitamente `p=0.001`, que es el valor fijado para nuestro experimento.

Para cada DEM pequeño, un programa Python independiente enumera todas las combinaciones de mecanismos de error, calcula su probabilidad, agrupa la masa por:

```text
(síndrome, máscara lógica completa)
```

y obtiene la respuesta joint-MAP exacta.

El decoder C++ debe coincidir con ese resultado en los 640/640 casos. Cualquier diferencia hace fallar el workflow.

## Criterio de aceptación

Una versión se considera válida únicamente si se cumplen simultáneamente:

```text
[PASS] SHA moderno exacto verificado
[PASS] upstream original compila y pasa sus tests
[PASS] extensión compila
[PASS] tests 2..64 observables pasan
[PASS] L63 funciona
[PASS] >64 observables se rechaza
[PASS] ranking modes y beam_eps pasan
[PASS] 640 casos generados
[PASS] oráculo exacto independiente generado
[PASS] decoder == oráculo en 640/640
[PASS] git diff --check limpio
```

GitHub Actions se utiliza aquí como entorno limpio de integración y reproducibilidad. **Sus tiempos no se consideran benchmark científico.**

## Cómo probar un DEM propio

Después de ejecutar el script de montaje queda compilado:

```text
.multiobs64-work/tesseract/bazel-bin/src/tesseract_trellis_diff_dump
```

El driver de validación trabaja con un `manifest.tsv` y DEMs individuales. Para añadir casos nuevos, lo recomendable es incorporarlos al corpus reproducible y, cuando sean suficientemente pequeños, hacer que también pasen por el oráculo exacto.

Para circuitos grandes donde la enumeración exacta no sea posible, la comprobación debe separarse en dos niveles:

1. corrección estructural/funcional y ausencia de regresiones;
2. experimento estadístico reproducible con semillas, configuración y corpus fijados.

## Qué NO hay que afirmar

No escribir en un artículo o correo que:

- hemos recuperado la versión privada;
- el código es idéntico al privado;
- tiene el mismo rendimiento que el privado;
- GitHub Actions demuestra aceleración;
- 640 casos pequeños prueban por sí solos corrección universal para cualquier DEM.

Sí podemos afirmar, si el workflow está verde, que hemos implementado **independientemente** soporte Trellis de hasta 64 observables sobre el SHA público moderno, que conserva la semántica joint-MAP derivada del linaje público, que pasa regresiones y pruebas dirigidas, y que coincide con un oráculo probabilístico exacto independiente en un corpus determinista de 640 casos que incluye 8, 12 y 64 observables.

## Para Fran/JL: qué mirar primero

1. Ejecutar `bash scripts/build_and_test_tesseract_multiobs64.sh`.
2. Comprobar que termina con `PASS`.
3. Abrir `exact-validation-summary.json` y verificar `"success": true`.
4. Abrir `tesseract-multiobservable64.patch` para ver exactamente lo añadido al upstream.
5. Si se quiere validar un circuito adicional, añadirlo como caso separado antes de hacer cambios en el algoritmo.
