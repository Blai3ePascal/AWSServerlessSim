# P06c explicado para no tener que acordarme de una mierda

## Qué estamos intentando demostrar ahora

P05 es nuestra referencia sencilla basada en el linaje público antiguo de Trellis.

P06 es nuestra versión moderna experimental que permite entre 2 y 64 observables.

Hasta ahora ambos habían pasado pruebas hechas a mano y pequeños oráculos exactos. Eso está bien, pero todavía podríamos haber tenido suerte y haber probado sólo casos bonitos.

P06c hace algo bastante más bruto: genera muchos problemas distintos, se los da **exactamente igual** a P05 y a P06 y mira si contestan lo mismo.

La pregunta de P06c es simplemente:

> Para el mismo DEM y el mismo síndrome, ¿P05 y P06 devuelven exactamente la misma máscara lógica y el mismo `low_confidence`?

Si una sola respuesta es distinta, el workflow queda rojo.

## Cuántas cosas probamos

El corpus inicial tiene 640 casos.

Sale de combinar:

- 2, 8, 12, 32 y 64 observables;
- cuatro regímenes de probabilidad: alrededor de 0.001, 0.01, 0.05 y 0.15;
- cuatro modelos diferentes por combinación;
- los ocho síndromes posibles de tres detectores.

Eso son 5 × 4 × 4 × 8 = 640 comparaciones.

## Por qué aparece 0.001

Porque Fran aclaró que el benchmark de referencia que nos interesa usa p=0.001. Aquí no estamos reproduciendo todavía sus circuitos BB reales, pero sí incluimos problemas sintéticos en ese orden de probabilidad para no probar sólo errores artificialmente grandes.

## Qué coño es un DEM aquí

Es el modelo de errores que le damos al decoder.

Cada error puede activar detectores D0, D1, D2 y también uno o varios observables L0...L63.

El generador crea errores que compiten entre sí, algunos que afectan sólo a lógica y una probabilidad diminuta que sirve para obligar a que el modelo tenga exactamente el número de observables que queremos probar.

## Por qué sólo tres detectores

Porque en P06c queremos comparar **corrección semántica**, no rendimiento.

Con tres detectores podemos probar todos sus síndromes posibles de forma exhaustiva: 000, 001, 010, 011, 100, 101, 110 y 111.

Los problemas grandes vienen después.

## Por qué usamos beam_width=65536

Porque aquí no quiero que una diferencia aparezca simplemente porque un decoder podó antes que el otro.

P06c intenta evitar la poda práctica para preguntar: si ambos pueden conservar las explicaciones relevantes, ¿escogen la misma solución lógica?

Más adelante haremos una fase distinta donde bajaremos el beam y estudiaremos si la poda hace divergir resultados.

## Qué guardamos de cada caso

Para P05 y P06 guardamos:

- `case_id`;
- si terminó bien o lanzó un error;
- número de observables;
- `predicted_obs_mask`;
- `low_confidence`.

No usamos tiempos como resultado científico porque un runner compartido de GitHub Actions no es un banco de rendimiento controlado.

## Qué pasa si algo falla

No regeneramos el caso y hacemos como si no hubiera pasado nada.

La semilla maestra es fija: `20260910`.

Cada modelo tiene además su propia semilla derivada y su fichero `.dem` queda guardado en el artefacto.

Por tanto, si por ejemplo falla `obs64_p0_m2_s5`, podemos abrir exactamente ese DEM y volver a ejecutar exactamente el síndrome 5.

## Qué significa TODO VERDE

Que en los 640 casos P05 y P06 coinciden exactamente en la decisión lógica conjunta y en `low_confidence`.

Eso sería evidencia bastante más fuerte de que el port moderno conserva la semántica multiobservable de nuestra referencia pública.

NO significa que tengamos la rama privada de Google.

NO significa que el rendimiento sea el mismo.

NO significa que ya hayamos reproducido los BB reales de Fran.

## Qué significa ROJO

Que hemos encontrado algo interesante: un DEM concreto en el que las dos implementaciones no hacen lo mismo.

En ese caso el siguiente trabajo no es esconderlo, sino reducir ese DEM al caso mínimo que siga fallando y entender qué diferencia de algoritmo lo provoca.

## Orden correcto a partir de aquí

Si P06c queda verde, lo siguiente razonable es:

1. P06d: repetir diferencial variando `beam_width` para estudiar la poda.
2. Incorporar circuitos/DEM reales, empezando por los que podamos ejecutar con la información pública.
3. Probar específicamente los BB de 8 y 12 observables de Fran cuando tengamos los ficheros exactos.
4. Sólo después empezar la parte seria de rendimiento y paralelización en hardware controlado.

## Frase corta para acordarme

**P06c genera 640 problemas reproducibles, se los da a P05 y P06 y exige que contesten exactamente lo mismo. Si una sola máscara cambia, rojo.**
