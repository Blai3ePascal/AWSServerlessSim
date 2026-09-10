# P06 explicado sin humo

Esto es para mí, no para vender nada. Si vuelvo aquí dentro de dos meses y no me acuerdo de una mierda, con leer esto debería saber qué hicimos y qué falta.

## Qué queríamos hacer

En P05 conseguimos una referencia multiobservable basada en código público antiguo de Tesseract. Esa referencia ya pasó pruebas normales, pruebas puñeteras y una comparación contra fuerza bruta.

P06 consiste en meter esa idea en el Trellis moderno `024db1d3...` sin cargarnos lo que ya funciona.

## La idea más importante

No hemos convertido el kernel moderno entero en una cosa nueva.

Hemos hecho dos puertas:

- si el DEM tiene 0 o 1 observable, entra por el kernel moderno rápido de siempre;
- si tiene entre 2 y 64 observables, entra por nuestro kernel experimental multiobservable.

Esto es a propósito. Prefiero tener una ruta nueva más lenta pero fácil de comprobar que tocar el motor rápido y después no saber si una cagada viene de nuestra lógica o de una optimización.

## Qué guarda nuestro camino nuevo

Cada entrada lleva tres cosas:

1. el estado de detectores;
2. una máscara lógica completa de 64 bits (`obs_mask`);
3. la masa o probabilidad acumulada.

Cuando un error lógico ocurre, hacemos XOR con su máscara. Por tanto, dos cambios del mismo observable se cancelan.

Cuando varias explicaciones llegan al mismo estado de detectores y a la misma máscara lógica, sumamos sus masas.

Para decidir qué estados sobreviven al beam, sumamos primero toda la masa de cada estado de detectores sin tirar las máscaras lógicas que contiene. Esto imita la semántica que encontramos en el linaje público antiguo.

Al final, entre las máscaras lógicas compatibles con el síndrome, gana la máscara completa con más masa: joint-MAP.

## Qué NO hace todavía

La ruta multiobservable de P06a está capada a propósito:

- sólo `MassOnly`;
- `beam_eps = 0`;
- máximo 64 observables;
- `observable_probability()` para más de un observable devuelve NaN porque una sola probabilidad escalar sería engañosa;
- no estamos midiendo rendimiento;
- no hemos metido todavía BB grandes;
- no hemos demostrado equivalencia con ninguna rama privada.

No es una limitación escondida. Es la forma de comprobar primero que la lógica funciona y optimizar después.

## Qué hemos probado

El workflow hace tres cosas separadas.

Primero descarga una copia moderna completamente intacta y pasa sus tests. Esa es la referencia de que upstream estaba sano antes de tocar nada.

Después reconstruye P05 desde el ancestro público y vuelve a ejecutar sus 12 tests, incluido el oráculo exacto por fuerza bruta.

Por último aplica P06 a otra copia del moderno y ejecuta nuestros tests multiobservables.

En el primer run del moderno nuevo, nuestros 7 tests pasaron:

- máscara conjunta de dos observables;
- cancelación por XOR;
- caso donde joint-MAP no coincide con decidir cada bit por separado;
- `L63` aceptado;
- `L64` rechazado;
- ranking experimental no soportado rechazado de forma explícita;
- comparación con enumeración exacta para todos los síndromes de un modelo pequeño.

## El rojo raro del primer run

El primer P06 terminó rojo por un test upstream llamado literalmente `RejectsMoreThanOneObservable`.

Ese test decía, básicamente: "si el modelo tiene L0 y L1, el constructor tiene que fallar".

Claro: P06 existe precisamente para que eso deje de pasar.

Los otros seis tests upstream pasaron y nuestros siete tests nuevos también pasaron. Por tanto no era una regresión inesperada: era un contrato antiguo que acabábamos de cambiar deliberadamente.

Para no hacer trampas con los tests, no lo hemos borrado sin más. Lo sustituimos por un test explícito que documenta el nuevo contrato: múltiples observables están permitidos en la ruta experimental `MassOnly`.

## Qué tiene que significar el verde final

Cuando el run final quede verde, significará esto y sólo esto:

- el moderno original sigue pasando intacto;
- P05 sigue pasando sus 12 tests;
- el parche P06 compila;
- los comportamientos antiguos que no queríamos cambiar siguen pasando;
- el único contrato antiguo modificado es el que prohibía más de un observable;
- los 7 tests multiobservables modernos pasan;
- el modelo pequeño coincide con la solución exacta por fuerza bruta.

Eso es bastante para decir que tenemos un **primer port moderno multiobservable correcto en casos pequeños**.

No es bastante para decir que está terminado.

## Qué haría después

Antes de ponerle BB gordos, haría P06b: generar muchos DEM pequeños de forma determinista y comparar directamente:

`P05 referencia pública -> P06 moderno -> oráculo exacto`

Los tres tienen que dar la misma máscara.

Cuando eso aguante un corpus amplio, entonces sí tiene sentido empezar con BB mayores y medir memoria, estados, beam y tiempos.

## Cómo llamarlo sin inventarnos nada

Frase correcta:

> implementación experimental multiobservable para el Trellis moderno, basada en el linaje público y validada contra un oráculo exacto en casos pequeños

Frase que no debemos usar:

> hemos recuperado la versión privada de 64 observables de Google

No tenemos esa prueba.

## Resumen en cristiano

Encontramos que el Trellis antiguo público ya sabía llevar 64 bits lógicos por dentro. Hicimos una referencia P05 y la machacamos con tests. Después metimos una segunda puerta en el Trellis moderno: lo normal sigue entrando por el motor rápido de siempre y los modelos con 2..64 observables entran por nuestro camino. Ese camino ya compila y ha pasado sus pruebas exactas; ahora estamos cerrando el contrato de regresión para que el único cambio esperado sea precisamente que dos observables ya no hagan petar el constructor.
