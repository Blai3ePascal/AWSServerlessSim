# Trellis y la degeneración, explicado sin darle más vueltas

Fran ha aclarado la duda importante: está hablando del Trellis, no del Tesseract original.

El problema que quiere mirar es bastante concreto: el Trellis puede encontrar una explicación que cuadra con el síndrome, pero eso no garantiza que sea la mejor respuesta lógica. Puede haber varias explicaciones físicas distintas que terminan en la misma clase lógica y, si las miras una a una, puedes quedarte con la equivocada.

La prueba que hago aquí separa dos cosas.

Primero monto casos pequeños donde puedo calcular la respuesta exacta sin fiarme de Tesseract. Enumero todas las combinaciones de errores, agrupo las que dan el mismo síndrome y la misma máscara lógica y sumo sus probabilidades. Además busco a propósito casos donde el camino físico individual más probable apunta a una máscara, pero la suma de varios caminos de otra máscara gana. Es justo el problema que está describiendo Fran.

Después paso esos mismos casos por nuestro Trellis multiobservable. Con un beam enorme no debería haber una poda que cambie la decisión. Si el Trellis está haciendo bien la agregación tiene que coincidir con la clase lógica de mayor masa, no con el camino individual más probable.

También pruebo beam 1, 2, 4, 16 y 65536. Esto sirve para ver si al podar demasiado empezamos a perder la clase buena aunque la lógica de agregación sea correcta.

La segunda prueba usa los BB reales públicos de Google a p=0.001:

- [[72,12,6]] X y Z
- [[90,8,10]] X y Z
- [[108,8,10]] X y Z
- [[144,12,12]] X y Z

Para cada circuito uso exactamente la misma semilla y los mismos shots con beam 15, 64, 256 y 1024. Guardo errores, low-confidence y cuántas predicciones cambian respecto al beam más grande.

Lo de GitHub no lo voy a vender como rendimiento ni como LER serio. Aquí sólo quiero contestar tres preguntas:

1. ¿Nuestro Trellis suma de verdad las explicaciones degeneradas por clase lógica?
2. ¿Con beam grande coincide con un cálculo exacto independiente en los casos donde el mejor camino individual daría otra respuesta?
3. ¿En los BB reales la respuesta cambia al aumentar el beam o el problema sigue igual?

Si el primer punto falla, hay un bug conceptual y toca arreglarlo antes de cualquier otra cosa.

Si el primero sale bien pero los BB cambian mucho con el beam, el problema está bastante más cerca de la poda que de la agregación final.

Si el primero sale bien y los BB no cambian prácticamente nada con el beam pero siguen dando malos resultados, habrá que mirar otra parte del modelo/orden/ranking y no seguir aumentando el beam porque sí.

Todo parte del mismo Tesseract público congelado que ya veníamos usando:

`024db1d3b5b038f565c476dd1b51885271f7b0bf`

No se usa código privado ni se afirma que esto sea la implementación privada de los autores.
