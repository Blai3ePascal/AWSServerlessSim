# P06 — port seguro de multiobservable al Trellis moderno

## Objetivo

Pasar la semántica conjunta de P05 al Trellis moderno congelado en `024db1d3b5b038f565c476dd1b51885271f7b0bf` sin romper ni sustituir el kernel rápido actual de un observable.

## Lo que hay ahora en el moderno

El código moderno todavía conserva `uint64_t obs_mask` al parsear fallos y en `TesseractTrellisWideLayerTemplate`. La pérdida de generalidad ocurre después:

- el constructor rechaza `num_observables > 1`;
- al compilar capas, `obs_mask` se reduce a `bool toggles_observable`;
- cada estado guarda únicamente `mass0` y `mass1`;
- si un fallo lógico está presente, esas dos masas se intercambian;
- al final sólo se decide entre máscara 0 y máscara 1.

Esto es un kernel binario muy optimizado. No lo vamos a convertir a un mapa de 64 bits porque sería mezclar una optimización probada con nuestro experimento y luego no sabríamos qué hemos roto.

## Diseño P06a

### Camino A: 0 o 1 observable

Se mantiene el kernel compilado actual. La intención es que el diff dentro de ese camino sea mínimo y que las regresiones upstream sigan pasando sin cambiar expectativas.

### Camino B: 2..64 observables

Se añade un kernel experimental separado. Cada entrada tiene:

- estado de detectores;
- `uint64_t obs_mask` completo;
- masa;
- penalty/score cuando proceda.

La expansión hace XOR de la máscara completa. Las entradas con el mismo estado de detectores se agrupan para calcular la masa total usada por el beam, pero las diferentes máscaras lógicas se conservan por separado dentro del estado.

Al final, para el estado detector válido, se agrega masa por máscara completa y se devuelve la máscara joint-MAP.

## Primera versión deliberadamente conservadora

P06a prioriza **corrección**, no velocidad. Si hace falta, la primera ruta multiobservable sólo soportará `MassOnly`. Los modos de ranking con future detcost se incorporarán después de que la comparación exacta y diferencial esté cerrada.

Esto evita fingir que una implementación recién escrita ya reproduce todos los detalles del kernel optimizado.

## Tests obligatorios

1. Todos los tests upstream del moderno, sin cambiar su resultado.
2. Los casos P05 de 2, 8, 12 y 64 observables.
3. Todos los casos adversariales P05b.
4. El mismo pequeño oráculo exacto por enumeración.
5. Casos de un observable comparados contra el kernel moderno original.
6. Diferencial moderno-multiobs versus referencia pública P05 para un corpus pequeño común.

## Qué NO significa P06

No significa equivalencia con una rama privada de Google. Significa que hemos portado a la arquitectura moderna una semántica que:

- procede de evidencia pública del propio historial de Trellis;
- ha sido comprobada contra casos exactos pequeños;
- se compara de forma diferencial contra nuestra referencia P05.

## Cuándo podremos probar BB grandes

Sólo después de que P06 pase los tests exactos y diferenciales. Los BB grandes sirven para ver comportamiento y escalabilidad; no son una buena herramienta para descubrir primero si hemos implementado mal una XOR o una agregación de masa.
