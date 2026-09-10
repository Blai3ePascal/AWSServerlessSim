# P06d — explicado para no tener que acordarme de una mierda

## La pregunta que estamos intentando contestar

Hasta P06c teníamos una cosa bastante buena: P05 y P06 daban exactamente la misma respuesta en 640 casos, incluidos casos de 64 observables.

Pero había una pega importante: P05 también es una reconstrucción nuestra basada en el código público antiguo. Si P05 y P06 compartieran el mismo error conceptual, podrían coincidir 640/640 y seguir estando los dos mal.

P06d existe para quitar esa duda.

## Qué hacemos ahora

Metemos un tercer juez que NO usa Tesseract.

Es un script Python muy tonto a propósito. Lee la lista de errores de cada DEM y prueba todas las combinaciones posibles de esos errores: ninguno ocurre, ocurre sólo el primero, ocurre el primero y el tercero, etc. Para cada combinación calcula:

1. qué detectores se encienden;
2. qué observables lógicos cambian, usando XOR;
3. qué probabilidad tiene exactamente esa combinación.

Después agrupa todas las combinaciones que producen el mismo síndrome. Dentro de ese síndrome suma la probabilidad de cada máscara lógica completa y escoge la máscara con más masa.

Eso es nuestro `joint-MAP` exacto.

## Por qué esto es bastante mejor que P06c

P06c preguntaba: «¿P05 y P06 hacen lo mismo?».

P06d pregunta: «¿P05 y P06 hacen lo mismo que el resultado matemático obtenido enumerando todas las posibilidades?».

Es decir, ya no ponemos a una versión nuestra de profesor de la otra.

## Qué corpus usamos

Reutilizamos exactamente el corpus reproducible de P06c:

- 80 DEM distintos;
- 640 casos en total;
- 2, 8, 12, 32 y 64 observables;
- 4 regímenes de probabilidad, incluido el entorno de `p = 0.001`;
- 3 detectores y sus 8 síndromes posibles;
- semillas fijas;
- `beam_width = 65536` para que esta fase estudie corrección y no poda agresiva.

Cada DEM tiene 14 mecanismos de error independientes. El oráculo puede probar sus `2^14 = 16384` combinaciones exactas sin ningún problema.

## Cuándo consideramos P06d verde

Sólo queda verde si se cumplen TODAS estas cosas:

- el corpus vuelve a tener 640 casos;
- el oráculo exacto puede resolver los 640;
- P05 sigue pasando sus tests anteriores;
- P06 sigue pasando sus tests y regresiones anteriores;
- P05 produce 640 respuestas;
- P06 produce 640 respuestas;
- P05 coincide con el oráculo exacto en los 640;
- P06 coincide con el oráculo exacto en los 640;
- no falta ningún caso;
- el artefacto de evidencias se genera aunque haya un fallo.

Si falla un solo caso, el workflow debe quedar rojo y guardar el `case_id`, el DEM, la semilla, la respuesta exacta, la de P05 y la de P06.

## Qué podremos decir si queda verde

Podremos decir que nuestra implementación moderna P06, hasta 64 observables, reproduce la decisión joint-MAP exacta en este corpus exhaustivamente verificable y que además conserva las regresiones que ya habíamos comprobado.

Eso es una afirmación mucho más fuerte que decir «funciona en mis ejemplos».

## Qué NO podremos decir todavía

No podemos decir que sea literalmente la versión privada que mencionó Fran. No tenemos ese código privado ni una salida de referencia de esa implementación.

Tampoco podemos decir todavía que P06 tenga el mismo rendimiento, las mismas optimizaciones o todos los modos de ranking de esa versión privada.

Y los tiempos de GitHub Actions siguen sin valer como benchmark científico.

## En qué punto encaja lo de Fran

Si el problema de Fran era «el Trellis público no me deja trabajar con códigos que tienen más de un observable y la versión interna llega hasta 64», nuestro P06 intenta resolver exactamente ese bloqueo funcional.

Si lo que necesitamos es demostrar «esto es idéntico a la versión privada de los autores», sólo se puede cerrar comparando contra esa versión si nos la facilitan o si sus autores confirman la semántica/salidas.

## Después de P06d

Si esto queda verde, el siguiente paso que merece la pena no es fabricar otros cien tests parecidos. Es meter los DEM/circuitos BB reales de 8 y 12 observables que está usando Fran y comprobar el decoder sobre el problema real. En paralelo se puede empezar a estudiar poda (`beam_width`) y después los modos de ranking/GARI, pero sin mezclarlo con esta validación de corrección.
