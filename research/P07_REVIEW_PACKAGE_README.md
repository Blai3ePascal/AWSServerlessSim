# Paquete de revisión antes de hacer experimentos serios

Este paquete existe para que otra persona pueda revisar **qué hemos cambiado, qué hemos probado y qué NO estamos afirmando todavía** antes de gastar tiempo en experimentos de LER/rendimiento.

## Qué problema estamos intentando resolver

La línea pública moderna de `quantumlib/tesseract-decoder` que congelamos en este trabajo está orientada a un único observable en Trellis. Nosotros hemos reconstruido de forma experimental un camino multiobservable de **2 a 64 observables** usando únicamente información pública y manteniendo intacto el camino optimizado de 0/1 observable.

No tenemos ni afirmamos tener la versión privada de Google. Tampoco afirmamos equivalencia bit a bit con ella.

## Fuente congelada

Repositorio público:

`quantumlib/tesseract-decoder`

Commit exacto:

`024db1d3b5b038f565c476dd1b51885271f7b0bf`

Todo el paquete se reconstruye a partir de ese SHA.

## Semántica experimental que estamos usando

Para 2..64 observables usamos una máscara `uint64_t` y propagación XOR de los observables.

Las entradas se distinguen por `(estado_de_detectores, mascara_logica)` y las masas de explicaciones equivalentes se agregan antes de seleccionar el resultado lógico.

La salida es **joint-MAP sobre la máscara lógica completa**, con desempate determinista hacia la máscara numéricamente menor.

Actualmente este camino experimental se limita deliberadamente a:

- `MassOnly`
- `beam_eps = 0`
- máximo 64 observables

El camino moderno de 0/1 observable se conserva separado.

## Qué pruebas hay antes de los BB reales

P06/P06b contiene pruebas exactas y adversariales para:

- dos observables;
- cancelación XOR;
- joint-MAP frente a decisiones independientes por bit;
- observable 63 aceptado y 64 rechazado;
- rechazo explícito de rankings todavía no soportados;
- comparación con enumerador exacto en modelos pequeños;
- desempate determinista;
- suma de varias explicaciones antes de elegir máscara;
- devolución ordenada de varios bits lógicos;
- paridad de hits de detectores duplicados;
- `low_confidence` ante detectores inválidos.

El checkpoint P06b terminó con 12/12 tests verdes.

## Qué prueba P07a

P07a deja los ejemplos de juguete y usa circuitos BB reales del `testdata` público a `p=0.001`:

- `[[72,12,6]]` X y Z;
- `[[90,8,10]]` X y Z;
- `[[108,8,10]]` X y Z;
- `[[144,12,12]]` X y Z.

El auditor comprueba el nombre/metadata, `p=0.001`, `r=d`, los observables esperados y SHA-256 de cada `.stim`.

Después Stim convierte cada circuito a DEM mediante la misma llamada `ErrorAnalyzer` usada por el CLI público, y se construye nuestro Trellis multiobservable.

Checkpoint P07a bueno:

- run: `34473973542`
- commit del harness: `aab3dea73759a738e15f970722ca12c435fd3831`
- 8/8 circuitos construidos;
- regresión Trellis compatible: verde;
- P06/P06b: 12/12 verde;
- artifact: `10150753712`;
- digest del artifact: `sha256:8074b99bf492c156b07f5c7d56c352d5a8e90d906871d6737311b0a4f100ecfe`.

Hubo un run rojo anterior por whitespace al final de `src/BUILD`. No llegó a compilar y no fue un fallo del decoder. Está conservado como provenance, no como resultado científico.

## Qué añade P07b

P07b ejecuta un **shot determinista por cada uno de los ocho circuitos**.

Para cada shot se conserva:

- circuito y SHA-256;
- seed;
- síndrome (lista de detectores activados);
- máscara lógica verdadera producida por Stim;
- máscara predicha por nuestro Trellis;
- si ambas coinciden;
- `low_confidence`;
- estados expandidos y fusionados;
- máximo beam y ancho de frontera.

Un error lógico o `low_confidence` **NO hace rojo el CI**. Es un dato experimental que debe conservarse. El CI sólo se pone rojo si el camino técnico falla, se cuelga o produce un registro inválido.

P07b sigue siendo smoke/integración. Un shot por circuito no permite estimar LER.

## Qué NO demuestra este paquete

Este paquete NO demuestra todavía:

- equivalencia con una implementación privada de Google;
- reproducción de las curvas/resultados del paper;
- LER científicamente estimado;
- LER por ronda;
- rendimiento o escalabilidad;
- validez de tiempos medidos en GitHub Actions;
- soporte multiobservable de `FutureDetcost` o `beam_eps > 0`.

Por eso todos los resultados de estas fases llevan:

`benchmark_valid=false`

`timing_metrics_interpretable=false`

Y P07b además:

`scientific_ler_valid=false`

## Qué debería revisar otra persona

La revisión que necesitamos antes de lanzar experimentos serios es:

1. ¿La semántica joint-MAP de máscara completa es razonable/correcta para el objetivo multiobservable?
2. ¿La agregación por `(estado, máscara lógica)` mantiene la probabilidad que esperamos?
3. ¿El beam debe contar estados de detector agregados como lo hacemos, preservando dentro de cada estado las máscaras lógicas?
4. ¿Hay alguna incompatibilidad conceptual con cómo Tesseract/Trellis debería tratar los observables BB?
5. ¿Los límites deliberados `MassOnly`, `beam_eps=0` y `<=64` son aceptables como baseline experimental?
6. ¿Falta alguna prueba de corrección imprescindible antes de medir LER?
7. ¿Hay alguna razón para no usar estos cuatro BB públicos a `p=0.001` como primer corpus real?

## Cómo está organizado el ZIP

El workflow genera `review_bundle/` con:

- este README;
- documentación P05/P06/P07;
- scripts exactos de instrumentación;
- parche completo aplicado al SHA congelado;
- manifiesto de los ocho inputs y sus hashes;
- los ocho `.stim` seleccionados;
- resultados/logs P06/P07;
- copia del árbol fuente ya parcheado, excluyendo `.git` y salidas Bazel;
- `REPRODUCE.sh`;
- `SHA256SUMS`.

## Reproducción

La forma preferida es ejecutar `REPRODUCE.sh` en Linux con `git`, `python3` y Bazel/Bazelisk disponibles.

El script vuelve a clonar el SHA público congelado, aplica los mismos scripts y ejecuta las pruebas. Bazel puede necesitar red la primera vez para descargar dependencias públicas.

La copia `patched_source/` sirve para inspeccionar el resultado directamente sin tener que aplicar el parche a mano.

## Qué queremos que nos contesten

No necesitamos que el revisor diga todavía que el decoder es rápido ni que el paper está reproducido.

Necesitamos algo mucho más concreto:

**¿La extensión multiobservable y su contrato de corrección son suficientemente sólidos para empezar la campaña experimental de shots/LER, o hay que corregir algo antes?**
