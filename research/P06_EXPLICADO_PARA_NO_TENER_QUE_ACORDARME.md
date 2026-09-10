# P06 explicado para no tener que acordarme de una mierda dentro de seis meses

## Qué coño estamos haciendo aquí

Tenemos un Trellis moderno de Google que funciona bien, pero está hecho para **cero o un observable lógico**. Nosotros queremos probar si se puede llevar a **hasta 64 observables** sin destrozar lo que ya funciona.

La regla principal es: **primero que sea correcto y después ya veremos si corre como un demonio**.

Por eso no hemos cogido el kernel moderno rápido y lo hemos llenado de cambios a lo loco. Hemos dejado el camino viejo para 0/1 observable y hemos creado otro camino experimental para 2..64.

## Qué es `obs_mask` explicado sin ganas de sufrir

Piensa en un `uint64_t` como una fila de 64 interruptores.

- bit 0 = observable L0;
- bit 1 = observable L1;
- bit 2 = observable L2;
- ...
- bit 63 = observable L63.

Si un bit vale 1, ese observable está activado en la explicación que estamos siguiendo.

Ejemplo: máscara `3` en binario termina en `11`, así que significa L0 + L1.

## Por qué usamos XOR

Porque los observables lógicos se combinan por paridad.

En cristiano: si algo activa L0 una vez, L0 queda encendido. Si después otra cosa vuelve a activar L0, las dos activaciones se cancelan.

Es decir:

`1 XOR 1 = 0`

Esto es importante porque una implementación que haga OR en vez de XOR puede parecer que funciona en ejemplos fáciles y estar conceptualmente mal.

## Qué decisión toma nuestro decoder

No decide L0 por un lado, L1 por otro y luego pega los resultados.

Conserva las combinaciones completas y al final pregunta algo parecido a:

> Para este síndrome, ¿qué máscara lógica completa acumula más probabilidad?

Eso es lo que estamos llamando `joint-MAP`.

Puede dar una respuesta distinta de mirar cada bit por separado, y tenemos una prueba hecha precisamente para pillar ese error.

## Qué dejamos intacto

Para 0 o 1 observable seguimos usando el kernel moderno rápido que ya existía.

Para 2..64 entra nuestra ruta experimental.

Eso es deliberado: si mañana algo se rompe con dos observables, no quiero preguntarme si además hemos roto el camino clásico. Son dos caminos separados y sabemos cuál estamos probando.

## Limitaciones actuales a propósito

La primera ruta multiobservable sólo admite:

- `MassOnly`;
- `beam_eps == 0`.

Si alguien intenta usar uno de los rankings modernos que todavía no hemos validado, **fallamos explícitamente**. Prefiero que el programa diga no puedo hacer esto todavía a que devuelva una mierda con apariencia científica.

## Qué pasó con el correo rojo de GitHub

El primer P06 fue el run `34454002499` y GitHub lo marcó como fallo.

Al mirar de verdad los logs ocurrió esto:

- upstream moderno sin tocar: verde;
- referencia P05 reconstruida: 12/12 pruebas verdes;
- nuestro parche P06: aplicado correctamente;
- compilación de nuestro moderno multiobservable: verde;
- pruebas nuevas P06: 7/7 verdes;
- pruebas antiguas sobre la copia modificada: 6 verdes y 1 roja.

La roja se llamaba literalmente:

`RejectsMoreThanOneObservable`

Y su trabajo era comprobar que Trellis **rechazara** más de un observable.

Claro, nosotros acabábamos de implementar precisamente lo contrario: que Trellis pueda aceptar más de un observable.

Así que el CI estaba diciendo a la vez:

1. demuestra que soportas varios observables;
2. demuestra que sigues rechazando varios observables.

Eso era una contradicción del arnés de pruebas, no un bug de nuestro decoder.

## Cómo lo arreglamos sin esconder la mierda debajo de la alfombra

No quitamos la prueba sin más.

Tenemos dos copias del moderno en GitHub Actions:

### Copia limpia

No se toca nada.

Ejecuta **todos** los tests originales, incluido `RejectsMoreThanOneObservable`.

Esto sirve para demostrar que el SHA original sigue siendo reproducible y que no estamos inventándonos la baseline.

### Copia experimental

Aplicamos P06.

En esa copia cambiamos **sólo** la vieja expectativa `RejectsMoreThanOneObservable` por otra que comprueba lo que ahora debe ocurrir: que varios observables funcionen en el camino experimental `MassOnly`.

Las otras pruebas antiguas siguen ejecutándose igual.

Además tenemos nuestras pruebas nuevas, que son mucho más exigentes que simplemente comprobar que el constructor ya no lanza una excepción.

## Qué prueban las 7 pruebas P06

No hace falta memorizar sus nombres. Lo importante es que comprueban estas siete cosas:

1. Una máscara con L0 y L1 se conserva completa.
2. Dos activaciones iguales pueden cancelarse por XOR.
3. Joint-MAP no se confunde con decidir cada bit por separado.
4. L63 funciona, que es el último bit válido de un `uint64_t`.
5. L64 se rechaza porque ya necesitaríamos más de 64 bits.
6. Los rankings multiobservable que todavía no soportamos fallan claramente en vez de hacer cosas raras.
7. En problemas diminutos podemos enumerar todas las combinaciones posibles a mano mediante código y el Trellis da exactamente la misma respuesta para todos los síndromes probados.

## Para qué sirve P05 entonces

P05 es nuestra referencia sencilla y auditable basada en el linaje público antiguo de Trellis.

P06 es el intento de llevar esa semántica al código moderno.

La gracia es que P05 nos da algo contra lo que comprobar P06. Si escribiéramos P06 directamente y sólo viéramos que no explota, eso valdría bastante poco.

## Si vuelve a salir rojo, dónde mirar primero

- **Baseline moderna limpia roja:** problema de upstream, entorno, dependencias o reproducibilidad. No culpar primero a nuestro multiobservable.
- **P05 roja:** se ha roto la referencia/oráculo o el entorno que la reconstruye.
- **Aplicación del parche roja:** nuestro script ya no encaja exactamente con el SHA esperado. Hay que revisar el diff, no parchear a ciegas.
- **Build P06 rojo:** error real de integración/compilación.
- **Regresiones antiguas compatibles rojas:** probablemente hemos roto comportamiento que no teníamos intención de cambiar.
- **Pruebas P06 rojas:** aquí sí hay que sospechar directamente de nuestra lógica multiobservable.
- **Sólo `RejectsMoreThanOneObservable` rojo en una versión vieja del workflow:** el CI está usando todavía el contrato contradictorio que ya detectamos.

## Qué NO podemos decir todavía

No podemos decir que hemos reconstruido la versión privada de Google.

No podemos decir que esto tenga el mismo rendimiento que una implementación privada.

No podemos usar los tiempos de GitHub Actions como benchmark científico.

No hemos validado todavía multiobservable con todos los rankings modernos.

No hemos validado todavía `beam_eps != 0` en multiobservable.

No hemos hecho todavía la fase seria de BB grandes y escalabilidad.

Y tampoco sabemos todavía si esta estructura es la más rápida posible. Ahora mismo lo importante es que la respuesta sea correcta.

## La frase corta para acordarme de todo

**P05 nos dice qué respuesta debería salir. P06 mete esa idea en el Trellis moderno sin tocar el camino viejo de un observable. El primer correo rojo fue porque una prueba antigua exigía justamente que la nueva función no existiera.**
