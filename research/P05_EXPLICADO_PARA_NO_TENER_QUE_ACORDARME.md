# P05 explicado para no tener que acordarme de nada

Esto está escrito para que yo vuelva aquí dentro de dos meses, no me acuerde de una mierda y pueda entender qué hicimos sin tener que releer medio GitHub.

## Qué estamos intentando hacer

El Trellis moderno público de Google que estamos usando sólo deja trabajar con un observable lógico. O sea, en la práctica sabe manejar `L0`, pero no una salida conjunta tipo `L0 + L7 + L63`.

Lo interesante es que mirando hacia atrás en el historial público encontramos una versión antigua donde **ya existía un `uint64_t obs_mask`**. Traducido: el programa ya llevaba una especie de número de 64 bits donde cada bit representa un observable lógico.

Ejemplo muy bruto:

- bit 0 encendido = `L0`
- bit 1 encendido = `L1`
- bit 7 encendido = `L7`
- bit 63 encendido = `L63`

Por eso 64 observables caben exactamente en un `uint64_t`: índices `0..63`.

## Qué NO hemos hecho

No tenemos la versión privada de Google. No la hemos copiado, no la hemos visto y no podemos decir que esto sea exactamente lo que ellos tenían.

Lo que sí tenemos es código público antiguo que ya hacía casi todo el trabajo multiobservable. Nosotros estamos completando la parte que faltaba y comprobando que matemáticamente se comporta como esperamos.

Así que la frase correcta es:

> reconstrucción experimental basada en el linaje público del Trellis

La frase incorrecta sería:

> hemos reconstruido exactamente la versión privada de Google

Eso no lo sabemos.

## Qué hacía ya el código antiguo

El código antiguo guardaba, para cada estado del Trellis:

1. el estado de los detectores;
2. la probabilidad o masa de ese estado;
3. una máscara de observables de 64 bits.

Cuando aparece un error lógico hace XOR con esa máscara.

Esto del XOR es importante. Si `L3` cambia una vez, `L3` queda activo. Si cambia dos veces, se cancela:

`L3 XOR L3 = 0`

No estamos guardando una lista de cosas que han ocurrido. Estamos guardando la **paridad final** de cada observable lógico.

## Qué faltaba

Al final del código antiguo aparecía la chapuza histórica: aunque todo el camino podía llevar una máscara de 64 bits, la reconstrucción final sólo miraba dos casos:

- máscara 0
- máscara 1, que equivale a `L0`

O sea: el motor llevaba más información de la que luego utilizaba.

Nuestro cambio P05 hace que al final no pregunte sólo si gana `0` o `L0`. Ahora mira las máscaras completas y escoge la máscara conjunta con mayor masa.

## Qué significa "máscara conjunta"

Supongamos que después de ver un síndrome tenemos estas posibilidades:

- nada: 20 %
- `L0`: 40 %
- `L1`: 35 %
- `L0+L1`: 5 %

La respuesta conjunta más probable es `L0` porque 40 % es el valor mayor.

Esto **no es lo mismo** que mirar cada bit por separado. En algunos casos cada observable individual puede estar por debajo del 50 %, pero una máscara concreta sigue siendo la combinación más probable de todas.

Por eso estamos haciendo joint-MAP y no 64 decisiones independientes.

## Qué pasó en P05a

GitHub Actions hizo desde cero lo siguiente:

1. descargó el Trellis moderno congelado en `024db1d3b5b038f565c476dd1b51885271f7b0bf`;
2. descargó el ancestro público en `56996facf54c25e6c08fed19d8902f40e1971f55`;
3. comprobó que los SHA eran exactamente esos;
4. ejecutó los tests originales del Trellis moderno sin modificarlo;
5. aplicó nuestro parche sólo al ancestro público;
6. compiló;
7. probó 1, 2, 8, 12 y 64 observables;
8. comprobó `L63`;
9. comprobó que `L64` se rechaza porque sería el observable número 65;
10. volvió a ejecutar regresiones del código antiguo;
11. guardó logs, patch, hashes y documentación como artifact.

Resultado del primer run: **todo verde**.

Run: `34452691614`

Artifact: `tesseract-p05-multiobservable-evidence-34452691614`

Artifact ID: `10142328424`

SHA256 del ZIP: `1f6bec32db39920b6316f970f2f27ce09c73a2db60edb03476f5b86df75bd1ac`

## Qué estamos haciendo en P05b

Ahora intentamos romper nuestro propio invento.

Las pruebas nuevas son deliberadamente puñeteras:

- dos `L3` que deben cancelarse por XOR;
- dos máscaras lógicas distintas que explican el mismo síndrome;
- un caso donde joint-MAP y decidir cada bit por separado dan respuestas diferentes;
- empate exacto entre dos máscaras para comprobar que el resultado no cambia de una ejecución a otra;
- un error lógico sin ningún detector;
- un modelo pequeño que podemos resolver por fuerza bruta enumerando todas las combinaciones y comparando el resultado exacto con el Trellis.

La prueba de fuerza bruta es la más importante. Ahí no confiamos en "creo que debería salir L2". Calculamos todas las combinaciones posibles de cinco errores, sus probabilidades, el síndrome que producen y la máscara lógica final. Luego agrupamos por síndrome y vemos cuál es realmente la máscara con más probabilidad. El Trellis tiene que dar exactamente lo mismo.

## Qué significa que esto pase

Si P05b sale verde, podremos decir algo bastante concreto:

> nuestra reconstrucción pública reproduce correctamente la semántica conjunta de observables en los casos pequeños donde podemos calcular la respuesta exacta.

Eso ya sirve como **oráculo de corrección** para el siguiente paso.

No significa todavía:

- que sea igual que la rama privada;
- que sea rápido;
- que escale bien a BB grandes;
- que la implementación moderna esté terminada.

## Qué haremos después

El siguiente paso es coger el Trellis moderno, que está mucho más optimizado, y añadir una ruta multiobservable separada.

No quiero cargarnos el camino rápido actual de un observable. La idea es:

- si hay 0 o 1 observable: usar exactamente el camino moderno rápido de siempre;
- si hay 2..64: usar nuestra ruta experimental multiobservable;
- para casos pequeños: ejecutar los dos mundos que podemos comparar y comprobar que la ruta moderna nueva da exactamente la misma máscara que nuestra referencia P05;
- sólo cuando eso sea estable: meter los BB grandes.

## Regla para no liarla

`main` no se toca con esto.

La baseline `024db...` no se modifica.

Cada cosa experimental va en su rama y el workflow guarda evidencia.

Si algún día nos dan la rama privada real, **no se mete en este repositorio público**. Esa rama serviría como oráculo externo en un entorno privado para comprobar si nuestra reconstrucción coincide o no.

## Resumen de una línea

Encontramos que el código público antiguo ya llevaba una máscara de 64 observables por dentro, completamos la reconstrucción final, lo estamos machacando con tests y, si aguanta, lo usamos como referencia para construir la versión moderna de 64 observables sin cargarnos el Trellis actual.
