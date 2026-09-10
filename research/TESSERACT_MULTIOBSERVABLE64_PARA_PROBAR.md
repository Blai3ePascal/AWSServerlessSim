# Tesseract Trellis con 0..64 observables — guía para probarlo sin saber nada del proyecto

## Qué problema resuelve

El Trellis moderno público que usamos como base está fijado exactamente en:

`quantumlib/tesseract-decoder@024db1d3b5b038f565c476dd1b51885271f7b0bf`

Ese código ya transporta un `uint64_t obs_mask` en las faltas y en las plantillas del Trellis, pero el constructor público rechaza más de un observable y el kernel compilado está especializado en las dos masas `mass0/mass1` de un único observable.

Esta rama añade una implementación independiente para **2..64 observables** sin tocar el camino rápido existente para **0 o 1 observable**.

El objetivo funcional es que un DEM con 8, 12 o hasta 64 observables lógicos pueda decodificarse devolviendo la **máscara lógica completa** predicha, en lugar de abortar simplemente porque existe `L1`, `L2`, etc.

## La prueba rápida: un comando

Desde la raíz de este repositorio:

```bash
python3 scripts/reproduce/verify_tesseract_multiobservable64.py
```

El script hace todo lo siguiente automáticamente:

1. crea un directorio aislado en `.work/tesseract-multiobservable64`;
2. clona `quantumlib/tesseract-decoder`;
3. fuerza el SHA exacto `024db1d3b5b038f565c476dd1b51885271f7b0bf`;
4. aplica las transformaciones P06 + P06b + P07;
5. adapta únicamente la antigua prueba upstream cuyo contrato era «rechazar >1 observable»;
6. ejecuta `git diff --check`;
7. genera el parche final en `.work/tesseract-multiobservable64/reports/tesseract-multiobservable64.patch`;
8. compila y ejecuta las regresiones upstream compatibles;
9. ejecuta todas las pruebas modernas multiobservable;
10. termina con `SUCCESS` sólo si todo lo anterior acaba correctamente.

### Requisitos

Necesitas:

- `git`;
- Python 3;
- Bazel/Bazelisk accesible como comando `bazel`;
- acceso a GitHub para clonar el repositorio público upstream.

No necesitas AWS, credenciales cloud, Sinter ni código privado.

## Qué hemos añadido exactamente

### 1. Límite explícito de 64 observables

Los índices `L0..L63` caben en un `uint64_t`. `L64` implicaría 65 observables y se rechaza explícitamente.

No se truncan bits y no se hace wrap-around.

### 2. El camino antiguo de 0/1 observable se conserva

Si `num_observables <= 1`, se sigue construyendo el kernel compilado moderno original.

La implementación multiobservable entra sólo cuando `num_observables > 1`.

Esto reduce el riesgo de romper el caso público que ya funcionaba.

### 3. Estado lógico completo, no bits independientes

Cada hipótesis multiobservable transporta:

```text
(detector_state, obs_mask, probability_mass, ranking_penalty)
```

`obs_mask` es un `uint64_t`. Los observables se actualizan con XOR porque representan paridad lógica.

Ejemplo:

```text
obs_mask = 0b101
```

representa `L0 + L2`.

### 4. La decisión final es joint-MAP

Para el síndrome observado, el decoder suma la masa de todas las explicaciones que acaban en la misma máscara lógica completa y elige la máscara completa con mayor masa.

No decide cada observable por separado.

Formalmente, la decisión que implementamos es:

```text
argmax_m P(observable_mask = m | syndrome)
```

con desempate determinista a favor de la máscara numéricamente menor.

### 5. Varias explicaciones de la misma máscara se suman

Dos caminos diferentes que producen el mismo `(detector_state, obs_mask)` no compiten entre sí: sus masas se agregan.

Esto evita confundir «camino individual más probable» con «clase lógica completa más probable».

### 6. El beam sigue siendo un beam de estados detectores

Éste es un detalle especialmente importante.

Si un mismo estado detector tiene 20 máscaras lógicas posibles, esas 20 máscaras **no consumen 20 posiciones del beam**.

Primero se suma la masa de todas las máscaras que pertenecen al mismo estado detector. Después se decide qué estados detectores sobreviven a la poda. Si un estado detector sobrevive, se conservan todas sus máscaras lógicas asociadas.

Eso mantiene la semántica del linaje público antiguo y evita que aumentar el número de observables cambie artificialmente el significado de `beam_width`.

### 7. Los tres rankings modernos están soportados

La versión final admite:

- `MassOnly`;
- `FutureDetcostRanked`;
- `FutureActiveDetcostRanked`.

Para los dos rankings con coste futuro, la penalización se calcula por **estado detector**, igual que en el camino compilado moderno. La máscara lógica no altera artificialmente esa penalización.

### 8. `beam_eps` está soportado

La poda por masa acumulada usa la masa agregada del estado detector, no la masa de cada máscara lógica por separado.

El orden conceptual es:

1. agregar máscaras por estado detector;
2. calcular score del estado;
3. aplicar `beam_width`;
4. aplicar el objetivo de masa de `beam_eps`;
5. conservar todas las máscaras pertenecientes a los estados seleccionados.

### 9. `decode()` devuelve todos los observables activos

Por ejemplo, una máscara con los bits 2 y 11 devuelve:

```text
{2, 11}
```

El bit 63 también está cubierto por pruebas.

### 10. `observable_probability()` no inventa un escalar ambiguo

La API original devuelve una probabilidad escalar porque sólo existía un observable.

Con múltiples observables no existe un único escalar equivalente que describa la distribución completa. Por eso, para `num_observables > 1`, `observable_probability()` devuelve `NaN` de forma deliberada.

La predicción multiobservable válida es `predicted_obs_mask` / `decode()`.

## Qué pruebas se ejecutan

### Regresiones del Trellis moderno

Se ejecuta el conjunto upstream `//src:tesseract_trellis_tests` sobre la versión extendida, sustituyendo únicamente la expectativa obsoleta que exigía rechazar más de un observable.

La baseline upstream sin modificar se ejecuta por separado en GitHub Actions.

### 17 pruebas modernas multiobservable

P06/P06b/P07 cubren, entre otras cosas:

- máscara conjunta con dos observables;
- XOR y cancelación lógica;
- caso donde joint-MAP no equivale a decidir bits independientemente;
- `L63` aceptado;
- `L64` rechazado;
- suma de varias explicaciones de una misma máscara;
- desempate determinista;
- `decode()` con bits altos;
- detectores repetidos por paridad;
- detector inválido y `low_confidence`;
- los tres modos de ranking;
- `beam_eps` con varios observables;
- `beam_width` contado por estado detector y no por máscara;
- `decode_shots()` con máscaras completas.

### Oráculo exacto independiente: 640/640 casos

GitHub Actions genera un corpus determinista que no depende de Tesseract para decidir la respuesta correcta:

- 80 DEM diferentes;
- 2, 8, 12, 32 y 64 observables;
- probabilidades base `0.001`, `0.01`, `0.05` y `0.15`;
- cuatro modelos por combinación;
- tres detectores;
- los ocho síndromes de esos tres detectores;
- 14 mecanismos independientes por DEM;
- 16 384 combinaciones exactas de errores por DEM;
- `beam_width=65536` para estudiar corrección sin introducir poda agresiva.

Total: **640 decisiones decodificadas y comparadas contra enumeración probabilística exacta**.

El oráculo enumera todas las combinaciones de errores, calcula el síndrome y la máscara lógica por XOR, suma probabilidades por `(syndrome, logical_mask)` y obtiene el joint-MAP exacto. No llama al decoder para decidir cuál es la respuesta esperada.

## GitHub Actions: validación completa

Workflow:

```text
.github/workflows/tesseract-multiobservable64-production.yml
```

Debe quedar verde sólo si pasan todos estos contratos:

1. SHA upstream correcto;
2. baseline upstream limpia;
3. referencia histórica pública P05;
4. aplicación reproducible P06/P06b/P07;
5. `git diff --check`;
6. regresiones modernas;
7. pruebas multiobservable;
8. generación de 640 casos;
9. oráculo exacto independiente;
10. 640 resultados de referencia;
11. 640 resultados de producción;
12. coincidencia completa con el oráculo;
13. empaquetado del parche, logs, DEM, metadatos y `SHA256SUMS`.

## Cómo aplicar los cambios manualmente

Si alguien quiere inspeccionar cada etapa en vez de usar el verificador:

```bash
git clone https://github.com/quantumlib/tesseract-decoder.git tesseract-multiobs64
cd tesseract-multiobs64
git checkout 024db1d3b5b038f565c476dd1b51885271f7b0bf
cd ..

python3 scripts/instrument/apply_p06_modern_multiobs.py \
  --upstream-dir tesseract-multiobs64 --report p06.json

python3 scripts/instrument/apply_p06_expected_upstream_contract.py \
  --upstream-dir tesseract-multiobs64 --report p06-contract.json

python3 scripts/instrument/apply_p06b_modern_multiobs_edge_tests.py \
  --upstream-dir tesseract-multiobs64 --report p06b.json

python3 scripts/instrument/apply_p07_complete_multiobs64_modes.py \
  --upstream-dir tesseract-multiobs64 --report p07.json

cd tesseract-multiobs64
git diff --check
bazel test //src:tesseract_trellis_tests \
           //src:tesseract_trellis_modern_multiobs_tests \
           //src:tesseract_trellis_multiobs64_modes_tests \
           --test_output=errors
```

## Qué significa que esto «cubre la privada» y qué NO significa

La capacidad que necesitábamos cubrir era la que no existe en la interfaz pública fijada: poder trabajar con **más de un observable y hasta 64 observables**.

Esta implementación cubre esa capacidad funcional y añade además un contrato explícito para rankings, `beam_eps`, salida completa y validación independiente.

No afirmamos que el código sea una copia, reconstrucción binaria o implementación idéntica de una rama privada a la que no tenemos acceso. No conocemos sus estructuras internas ni sus optimizaciones.

La afirmación defendible es más fuerte y más limpia científicamente:

> Hemos implementado de forma independiente soporte Trellis para máscaras lógicas conjuntas de hasta 64 observables sobre el código público moderno, siguiendo la semántica visible en el linaje público y verificando la decisión joint-MAP contra enumeración probabilística exacta en un corpus reproducible.

## Qué falta después de esto

La siguiente validación útil no consiste en inventar otros cientos de DEM pequeños. Consiste en ejecutar esta versión sobre los **circuitos/DEM BB reales de 8 y 12 observables** del experimento y después estudiar escalabilidad/poda/rendimiento con metodología controlada.

Los tiempos de GitHub Actions son evidencia de integración, no benchmarks científicos.
