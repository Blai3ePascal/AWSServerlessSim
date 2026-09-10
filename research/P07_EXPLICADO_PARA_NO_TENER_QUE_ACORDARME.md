# P07 explicado para no tener que acordarme de otra puta carpeta dentro de seis meses

## Qué estamos haciendo ahora

Hasta P06 hemos demostrado que **nuestro Trellis modificado sabe llevar más de un observable sin hacerse un lío** en ejemplos pequeños donde podemos saber la respuesta correcta.

Ahora toca dejar de jugar sólo con ejemplos de juguete y meterle los circuitos BB reales que están en el repositorio de Google.

Los cuatro que nos interesan son:

- `[[72,12,6]]` -> 12 observables
- `[[90,8,10]]` -> 8 observables
- `[[108,8,10]]` -> 8 observables
- `[[144,12,12]]` -> 12 observables

Y queremos los de `p=0.001`.

## La confusión de los .dem y los .stim

Aquí hubo una cosa fácil de confundir.

Yo estaba buscando primero nombres cortos tipo `algo_0.001.dem`. Eso no es la forma en la que están guardados estos circuitos BB reales.

Los BB del repositorio están como ficheros `.stim` con nombres larguísimos que meten dentro casi toda la ficha del circuito: rondas, distancia, `p`, tipo X/Z, `nkd`, número de qubits y los polinomios.

Ejemplo de la idea del nombre:

`r=10,d=10,p=0.001,...,c=bivariate_bicycle_X,nkd=[[108,8,10]],....stim`

Por tanto: **no vamos a renombrar un 0.0001, ni fingir que es 0.001, ni escoger un fichero a ojo**.

El script P07 busca dentro del checkout exacto de Google y sólo acepta los que cumplen de verdad las condiciones.

## Qué exige P07a

P07a busca ocho ficheros en total:

- X y Z de `[[72,12,6]]`
- X y Z de `[[90,8,10]]`
- X y Z de `[[108,8,10]]`
- X y Z de `[[144,12,12]]`

Todos tienen que ser `p=0.001` y usamos `r=d`.

Además no se limita a fiarse del nombre. Abre el texto del circuito y comprueba que aparecen los observables que tienen que aparecer: de `L0` a `L11` cuando son 12, o de `L0` a `L7` cuando son 8.

Después calcula SHA-256 de cada fichero. Así dentro de seis meses podemos saber **qué fichero exacto usamos**, aunque alguien haya añadido veinte variantes al repositorio.

## Y después qué coño prueba

P07a no intenta todavía demostrar que decodificamos bien miles de shots.

Hace algo más básico y necesario:

1. abre el circuito `.stim` real;
2. Stim lo transforma al modelo de errores de detectores, el DEM;
3. mira cuántos detectores y observables salen realmente;
4. mete ese DEM grande y real en **nuestro Trellis P06**;
5. intenta construir el decoder con `MassOnly`, `beam_eps=0` y beam 15;
6. comprueba que el decoder sigue viendo los mismos 8 o 12 observables.

Si eso explota, ya sabemos que el problema está antes de empezar a decodificar shots. Eso es muchísimo mejor que lanzar una barbaridad de pruebas y recibir un rojo sin saber de dónde viene.

## Por qué no usamos directamente tesseract_trellis como comando

Hay una pequeña putada separada del kernel.

El `main` público moderno todavía tiene una comprobación que dice, básicamente: si hay más de un observable, me niego y cierro.

Eso es el **programa de línea de comandos**, no la parte del decoder que modificamos en P06.

Podríamos borrar esa comprobación en dos minutos, pero entonces mezclaríamos dos cambios a la vez. En P07a prefiero una sonda pequeñísima que llama directamente a la biblioteca real.

Si P07a sale verde, P07b será el sitio lógico para abrir el CLI o hacer un runner de shots controlado y empezar a decodificar de verdad.

## Primer rojo de P07a, para no volvernos locos dentro de seis meses

El run `34473807916` **sí encontró bien los ocho circuitos**. El auditor vio 14 ficheros `.stim` con `p=0.001` en la carpeta y seleccionó exactamente los ocho que queríamos. También comprobó los observables 12/8/8/12 y calculó sus hashes.

No llegó a compilar ni a construir ningún decoder. El paso de preparar el árbol falló porque `git diff --check` detectó una línea en blanco extra al final de `src/BUILD` generada por nuestro script de instrumentación.

Es decir: este rojo no significa nada sobre Tesseract, Stim, los BB o el soporte multiobservable. Es una mierda de whitespace de nuestro arnés. La corrección correcta es quitar sólo esa línea extra y volver a ejecutar exactamente el mismo contrato.

## Si P07a sale verde, qué podemos decir

Podemos decir:

- los cuatro BB reales de `p=0.001` están localizados de forma reproducible;
- tenemos X y Z de los cuatro;
- sus observables reales son 12/8/8/12 como esperamos;
- Stim puede convertir esos circuitos reales a DEM;
- nuestro P06 puede construir el Trellis sobre esos DEM multiobservable reales;
- y todo queda con nombres, hashes, logs y SHA congelado.

## Lo que NO podemos decir todavía

No podemos decir todavía:

- que ya hemos reproducido los resultados del paper;
- que tenemos la versión privada de Google;
- que somos equivalentes bit a bit a esa versión privada;
- que el decoder da el LER correcto en los BB;
- que un tiempo de GitHub Actions sirve como benchmark;
- ni que escalar a muchos shots vaya a ser barato en memoria.

Eso viene después.

## La frase importante de GitHub Actions

Todo lo que salga de esta fase tiene que llevar:

`benchmark_valid=false`

`timing_metrics_interpretable=false`

GitHub aquí sirve para decir **esto compila, esto es reproducible y esto funciona funcionalmente**. Para medir rendimiento de verdad usaremos una máquina controlada.

## Si se pone rojo, dónde mirar

Si falla el audit de inputs: falta un fichero, hay más de uno que cumple lo mismo, no es `p=0.001`, no es `r=d` o los observables del circuito no cuadran.

Si falla el parche P06: hemos roto nuestra base antes de llegar a BB.

Si falla el build de la sonda: la integración C++/Stim/Trellis no compila.

Si falla una sonda BB concreta: veremos en el log exactamente qué X/Z y qué `[[n,k,d]]` no puede convertirse o construir.

## Qué viene justo después

P07b: muy pocos shots, semillas fijas, resultado lógico real guardado, predicción guardada y `low_confidence` guardado. Primero queremos ver que el camino completo funciona.

P07c: sólo cuando eso esté estable, ampliar corpus y empezar a tener datos serios de corrección.

Y rendimiento, paralelización y escalado después. Antes no, porque optimizar una cosa que todavía no hemos demostrado que calcula lo correcto es hacer el gilipollas con más pasos.
