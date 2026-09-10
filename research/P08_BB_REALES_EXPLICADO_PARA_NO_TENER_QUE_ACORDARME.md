# P08 — BB REALES a p=0.001, explicado para no tener que acordarme de una mierda

## Qué estamos intentando demostrar

Hasta P06/P07 habíamos demostrado que **nuestro Trellis multiobservable calcula bien**: 2, 8, 12, 32 y 64 observables, casos borde, XOR, joint-MAP y 640 casos contra un oráculo exacto independiente.

Eso estaba muy bien, pero todavía había una pregunta muy tonta y muy importante:

> Vale, ¿y esto abre y decodifica de verdad los circuitos BB que nos interesan o sólo funciona en nuestros ejemplos pequeños?

P08 existe para contestar exactamente eso.

No estamos buscando la versión privada porque no la vamos a tener. Estamos construyendo una sustitución independiente usando sólo:

1. el Tesseract público de Google;
2. historial público del propio proyecto;
3. nuestra extensión multiobservable;
4. circuitos BB públicos del propio repositorio;
5. pruebas reproducibles.

**No hay código privado en esta rama.**

---

## Los cuatro BB que queremos

El patrón que necesitamos cubrir es **12 / 8 / 8 / 12 observables**. Las cuatro familias que usamos son:

| Nombre corto | Código | Observables lógicos `k` | Distancia `d` |
|---|---:|---:|---:|
| BB72 | `[[72,12,6]]` | 12 | 6 |
| BB90 | `[[90,8,10]]` | 8 | 10 |
| BB108 | `[[108,8,10]]` | 8 | 10 |
| BB144 | `[[144,12,12]]` | 12 | 12 |

Para cada familia probamos **X y Z**. Por tanto P08 intenta ejecutar 8 circuitos reales en total.

La probabilidad que fijamos es **p=0.001**, porque ésa es la que debemos usar en esta línea de trabajo. No se cambia un `0.002` por `0.001` con un buscar/reemplazar cutre: el script busca los ficheros públicos que ya están etiquetados por upstream como `p=0.001`.

---

## La cagada que encontramos antes de probarlos

El kernel que construimos ya aceptaba hasta 64 observables y las pruebas de C++ pasaban. Pero el programa `tesseract_trellis` que se ejecuta desde terminal conservaba esta puerta vieja del código público:

```text
si num_observables > 1 -> error y salir
```

O sea: habíamos arreglado el motor pero la puerta del garaje seguía cerrada.

Eso explica por qué **una prueba de la clase `TesseractTrellisDecoder` no basta para decir que Fran/JL pueden ejecutar un `.stim` real**.

P08 añade `scripts/instrument/apply_p08_cli_multiobs64.py`, que hace tres cosas pequeñas y explícitas:

1. cambia el límite viejo del CLI de `>1` por el límite real `>64`;
2. mantiene `--obs-probs-out` como función de **un único observable**, porque esa salida representa `P(L0=1)` y no debe fingirse que significa algo para una máscara conjunta de 8/12/64 bits;
3. añade `num_observables` al JSON de estadísticas para que la prueba pueda comprobar lo que el DEM ha entendido de verdad.

No cambia el algoritmo del Trellis. Sólo hace accesible desde el ejecutable la capacidad que ya hemos añadido y validado en el decoder.

---

## Qué significa `obs_mask` sin volverme loco

Si tenemos hasta 64 observables, usamos un entero de 64 bits como una caja con 64 interruptores:

- bit 0 -> `L0`
- bit 1 -> `L1`
- ...
- bit 63 -> `L63`

Si una explicación de error activa `L0` y `L3`, su máscara tiene esos dos bits encendidos.

Cuando combinamos fallos usamos **XOR**. Si un observable se activa dos veces, se cancela. Esto no es una decisión estética: es la paridad lógica que debemos conservar.

Al final no preguntamos por cada bit por separado. Elegimos la **máscara conjunta más probable** entre las explicaciones compatibles con el síndrome. Eso es lo que en la documentación técnica llamamos `joint-MAP complete logical mask`.

---

## Cómo encuentra P08 los circuitos sin hacer trampas

El script `scripts/find_p08_bb_circuits.py` entra en:

```text
testdata/bivariatebicyclecodes/
```

del checkout público congelado de Tesseract y busca por metadatos del propio nombre de fichero:

- `p=0.001`
- `nkd=[[n,k,d]]`
- `c=bivariate_bicycle_X` o `c=bivariate_bicycle_Z`
- `r=d`

Para cada código exige exactamente un X y un Z que cumplan el contrato.

Además calcula SHA-256 del `.stim` que se ha usado y hace una comprobación previa de `OBSERVABLE_INCLUDE`.

Luego viene una comprobación todavía mejor: **el propio Tesseract convierte el circuito a DEM y el CLI escribe `num_observables` en sus estadísticas**. P08 exige que ese número sea 12/8/8/12 según corresponda.

Así evitamos decir “este fichero debería tener 12” porque lo pone el nombre. Lo comprobamos también después de que Stim/Tesseract lo haya interpretado.

---

## Qué ejecutamos de verdad

Por cada uno de los ocho circuitos seleccionados, `scripts/run_p08_real_bb.py` ejecuta el binario real:

```text
tesseract_trellis --circuit <fichero real> --sample-num-shots ...
```

El programa:

1. abre el circuito Stim real;
2. lo convierte a un Detector Error Model usando Stim;
3. construye nuestro Trellis multiobservable;
4. muestrea un shot con semilla fija;
5. decodifica el síndrome;
6. compara la máscara predicha con los observables reales del shot cuando hay confianza;
7. guarda `num_errors` y `num_low_confidence`;
8. guarda el número de observables que vio el DEM.

En GitHub Actions usamos esta prueba como **integración/corrección**, no como benchmark de velocidad.

Los tiempos de un runner de GitHub no se usan para ninguna afirmación científica.

---

## Qué es PASS y qué NO es PASS

### PASS de P08 significa

- se encontraron los 8 circuitos públicos exactos que pedimos;
- son `p=0.001`;
- el patrón lógico es 12/8/8/12;
- la extensión se aplica sobre el SHA público congelado;
- compila;
- siguen pasando las regresiones antiguas y las pruebas 0..64;
- el CLI ya no rechaza 8/12 observables por la barrera antigua de `>1`;
- cada circuito se convierte a DEM;
- el DEM reporta el `k` correcto;
- se puede muestrear y pasar al decoder una entrada real;
- el proceso termina de forma controlada y deja estadísticas y logs.

### PASS de P08 NO significa

- que tengamos el código privado;
- que nuestro código sea idéntico al privado;
- que GitHub Actions haya demostrado que somos más rápidos;
- que un único shot mida LER con precisión;
- que un `low_confidence` deba esconderse;
- que ya tengamos el benchmark final del artículo.

Esto es la prueba de que la **capacidad funcional que necesitábamos existe en nuestra rama y llega hasta la interfaz real de uso**.

---

## Qué pasa con `low_confidence`

No se borra, no se convierte mágicamente en acierto y no se usa para maquillarnos una gráfica.

En P08 simplemente se registra. Estamos haciendo un smoke/integration test con beam finito.

Cuando hagamos evaluación científica, seguiremos la política conservadora que ya hemos fijado: los casos `low_confidence` se conservan y, cuando corresponda al protocolo del paper, se cuentan como fallos.

---

## Por qué no usamos Sinter

Porque no forma parte de esta solución y no lo necesitamos.

P08 llama directamente a `tesseract_trellis`, muestrea con Stim desde el propio ejecutable y guarda resultados deterministas por semilla.

---

## Cómo lo prueba otra persona

Desde nuestra rama P08:

```bash
git clone https://github.com/Blai3ePascal/AWSServerlessSim.git
cd AWSServerlessSim
git checkout research/tesseract-p08-bb-real-v2
bash scripts/build_and_test_tesseract_multiobs64_bb.sh
```

La persona no necesita tocar el repositorio de Google a mano. El script clona el upstream público y lo fija en:

```text
024db1d3b5b038f565c476dd1b51885271f7b0bf
```

Después aplica nuestras modificaciones de forma reproducible.

Si quiere ver exactamente qué hemos añadido al código original, el script genera:

```text
tesseract-multiobservable64-with-cli.patch
```

Ése es el fichero más cómodo para revisar el cambio sin leer todo nuestro arnés.

---

## Si falla, dónde miro

### Falla buscando un circuito

Mirar `bb-selection` / `selected-circuits.tsv`.

Significa que el checkout público no contiene exactamente el fichero esperado con esos metadatos. No significa que el decoder esté roto.

### Falla aplicando un parche

El upstream ya no coincide con el SHA para el que escribimos el parche o alguien ha modificado el árbol antes de tiempo.

### Falla compilando

Mirar `build-and-unit-tests.log`.

Esto sí puede ser una incompatibilidad de código/toolchain o una cagada nuestra.

### Sale el mensaje de “at most one observable”

La extensión del CLI **no se ha aplicado**. Ese texto viejo no debe sobrevivir en el árbol P08 modificado.

### El DEM dice 1 observable en BB72/90/108/144

Fallo serio de integración o circuito equivocado. P08 debe quedar rojo.

### El DEM dice 12/8/8/12 pero hay `low_confidence`

El soporte multiobservable está funcionando, pero el beam/ranking elegido no ha conservado una solución con confianza para ese shot. Se guarda y se estudia; no se oculta.

### El programa hace segfault/abort en un BB real

Fallo real. Guardar circuito, semilla, SHA y log y convertirlo en regresión.

---

## Qué le puedo decir a Fran si esto queda verde

La frase segura es:

> Hemos implementado de forma independiente sobre el Tesseract público una extensión del Trellis que conserva y decodifica una máscara lógica conjunta de hasta 64 observables. La hemos validado contra un oráculo exacto en 640 casos reproducibles y además la hemos probado desde el CLI sobre los circuitos públicos BB `[[72,12,6]]`, `[[90,8,10]]`, `[[108,8,10]]` y `[[144,12,12]]` a `p=0.001`, comprobando el patrón 12/8/8/12. Todo el cambio se entrega como patch reproducible y con tests.

Lo que **no** digo es:

> Hemos recreado la versión privada.

No lo sabemos y no nos hace falta afirmarlo.

---

## Resumen de una línea para mi yo del futuro

**P08 = coger nuestra versión 0..64 ya demostrada, abrir la puerta vieja del CLI que seguía limitada a 1, buscar los BB públicos reales a p=0.001 sin inventar ficheros y demostrar que 72/90/108/144 entran de verdad por el programa con 12/8/8/12 observables.**
