# Guion — presentación de avance IPD438

Meta: **13:30 min** (deja 1:30 de holgura sobre 15). Nadie en la sala es experto en video: cada sigla se explica la primera vez, con palabras simples. Las diapositivas tienen los conceptos; la explicación la das tú.

| # | Diapositiva | Pauta | Tiempo | Acumulado |
|---|---|---|---|---|
| 1 | Portada | Promesa | 0:15 | 0:15 |
| 2 | Índice | Organización | 0:15 | 0:30 |
| 3 | Cómo se comprime y se transmite el video | Contenidos previos | 1:15 | 1:45 |
| 4 | H.264 por dentro: de segmento a NAL | Contenidos previos | 1:15 | 3:00 |
| 5 | ¿Por qué perder un intra es tan grave? | Contenidos previos | 1:15 | 4:15 |
| 6 | AGiLE (1): GoP largo, entradas cada 2 s | Estado del arte | 1:15 | 5:30 |
| 7 | AGiLE (2): el edge decide | Estado del arte | 1:00 | 6:30 |
| 8 | FrameTrace y cómo se recupera uno hoy | Estado del arte | 1:15 | 7:45 |
| 9 | Transporte: SRT | Estado del arte / plataforma | 1:15 | 9:00 |
| 10 | Problema: el punto de quiebre | Problema y motivación | 1:30 | 10:30 |
| 11 | Objetivo | Objetivo + promesa | 1:15 | 11:45 |
| 12 | Resultados a producir | Resultado a reproducir | 0:50 | 12:35 |
| 13 | Costos | — | 0:40 | 13:15 |
| 14 | Referencias | Referencias | 0:15 | 13:30 |

Si vas atrasado: en la 8 no leas la tabla fila por fila (solo la última fila), y en la 13 nombra tres costos.

---

## 1. Portada (0:15)

> "Mi tema es cómo recuperar el video después de que se pierden paquetes, **sin pedirle nada al codificador**. Les voy a mostrar que el mecanismo para hacerlo ya existe en la red, y que hoy se bota."

Eso es la promesa: dila aquí y repítela en la 11.

## 2. Índice (0:15)

> "Primero, lo mínimo para entender cómo viaja el video. Después, los dos trabajos en que me apoyo, el transporte que voy a usar, el problema, mi objetivo y qué traigo para la final."

## 3. Cómo se comprime y se transmite el video (1:15)

- Un video son fotos, 30 por segundo. Sin comprimir, un 1080p son unos 750 Mb/s; nadie manda eso. H.264, el códec más usado, lo deja en unos 5.
- El truco: una foto se parece mucho a la anterior. Entonces de vez en cuando se manda una **foto completa (I)**, y entre medio solo **lo que cambió (P)**.
- Analogía: el I es la foto; cada P es "mueve esto un poco a la derecha". Sirve solo si tienes la imagen anterior.
- **IDR**: un I especial que además le dice al decodificador "empieza de cero".
- **GoP**: el grupo desde un I hasta el siguiente.
- Todo eso viaja en paquetes de unos 1300 bytes. Un I, que es grande, ocupa decenas de paquetes; un P, unos pocos.

## 4. H.264 por dentro: de segmento a NAL (1:15)

Recorre el dibujo de arriba hacia abajo:

- **Segmento**: el trozo de algunos segundos que el servidor guarda y reparte. Adentro hay GoPs.
- **GoP**: un I y sus P.
- **Slice**: un frame se puede partir en trozos que se decodifican solos; normalmente es uno por frame.
- **NAL**: la caja en que H.264 entrega cada trozo a la red. Su primer byte es una etiqueta que dice qué lleva: un slice normal, un IDR, parámetros, o una **SEI**.
- **SEI**: datos extra que el decodificador puede ignorar sin que pase nada. "Guárdenlo, porque ahí AGiLE esconde lo que me interesa."

## 5. ¿Por qué perder un intra es tan grave? (1:15)

- Como cada P es "lo que cambió respecto del anterior", si falta uno, todos los siguientes se aplican sobre una imagen equivocada. El error se arrastra hasta el próximo I: eso es la **propagación del error**.
- Señala el dibujo: perder un P daña hasta el final del GoP. Perder el I daña **todo el GoP**: con GoP 30 a 30 fps, un segundo completo.
- Perder el **IDR** es el peor caso: además se pierde la orden de "empieza de cero", el decodificador se desordena y la imagen se puede congelar.
- Y el I, por ser el más grande, es el que tiene más paquetes que perder.
- El decodificador puede **ocultar** el daño (congelar, repetir la imagen anterior), pero eso lo disimula; no lo arregla.
- Transición: *"Ahora, los trabajos en que me apoyo. Parto por el más importante."*

## 6. AGiLE [2] (1): GoP largo, entradas cada 2 s (1:15)

- Paper de **MMSys 2024**, de ByteDance (TikTok).
- Su problema: un GoP largo ahorra bits, pero el que se conecta a la transmisión tiene que esperar el próximo I para ver algo.
- Su idea: codificar con GoP largo, de 10 s, pero ofrecer puntos de entrada cada 2 s, el **pseudo-GOP**.
- En cada punto de entrada codifican la misma imagen **además** como I: el **I-header** (los cuadritos rojos).
- Ese I-header viaja escondido **dentro de una SEI**: un decodificador normal la ignora y sigue con sus P.

## 7. AGiLE [2] (2): el edge decide (1:00)

- El video pasa del codificador a la red de distribución (**CDN**) y llega al **edge**, el servidor más cercano al espectador.
- El edge lee la SEI y guarda el I-header. Si llega un espectador **nuevo**, le da el I-header y entra de inmediato. Al espectador **ya conectado** se lo descarta.
- Resultado: ahorran ~3,5 % de bits a igual calidad, a cambio de +2,8 % de datos hacia el CDN.
- Entrar por un I-header deja una diferencia mínima: ~1 punto de VMAF, una medida de calidad percibida de 0 a 100.
- Transición: *"Fíjense en el espectador conectado; vuelvo a él en el problema."*

## 8. FrameTrace [1] y cómo se recupera uno hoy (1:15)

- **FrameTrace**, de SIGCOMM 2025, midió frame a frame: con 1 % de pérdida, un GoP de medio segundo da calidad 72,6; uno de 2 s, 55,7. Refrescar seguido salva la calidad.
- Su controlador acorta el GoP cuando ve pérdida, pero para eso el receptor le tiene que avisar al codificador: eso es un **lazo**.
- La tabla resume las alternativas. Lee solo las columnas: o tienen lazo al codificador (pedir un intra, PLI) o se pagan siempre, aunque la red esté sana (GoP corto, refresco intra).
- Termina en la última fila: "Lo que no existe es algo sin lazo y sin costo cuando la red está sana."

## 9. Transporte: SRT (1:15)

- Para la plataforma uso **SRT**, un protocolo abierto sobre UDP hecho para video en vivo.
- Funciona con una latencia fija, por defecto 120 ms. Dentro de ese plazo, si al receptor le falta un paquete, lo pide (eso es el NAK, la flecha roja) y el emisor lo reenvía.
- Si el paquete no alcanza a llegar, SRT lo **descarta**. Esa pérdida sí llega al decodificador, y ahí es donde actúa mi propuesta.
- Lleva el video en MPEG-TS, el formato de la televisión digital, y puede cifrarlo.
- La ventaja clave para mí: el emisor, que en mi caso es el edge, **sabe qué paquetes descartó**. O sea, sabe a qué espectador le falta algo, sin preguntarle al codificador.

## 10. Problema: el punto de quiebre (1:30)

- Si los errores no se propagaran, no habría problema.
- Hoy, para cortar la propagación hay dos caminos: pedirle un intra al codificador (lazo: tarda un ida y vuelta y el intra le llega a todos) o mandar intras siempre (se paga aunque la red esté sana).
- **Quiebre**: AGiLE alarga el GoP a 10 s para ahorrar bits. Entonces una pérdida dura hasta 10 s.
- **Anomalía** (señala el dibujo): el espectador pierde algo a los 2,5 s y queda dañado 7,5 s. A los 4 s el edge ya tenía un I-header que lo arreglaba en 1,5 s… y se lo descartó, porque la regla es "solo para nuevos".
- Lee el bloque, despacio: **"El mecanismo para recuperarse de la pérdida ya está en la red, ya está pagado, y hoy se descarta."**
- Si te preguntan "¿pagado?": pagado hasta el edge. Al espectador solo le cuesta cuando se le entrega, y solo a quien lo necesita.

## 11. Objetivo (1:15)

- Lee el primer punto: demostrar que entregar el I-header a quien perdió paquetes corta el daño en la próxima frontera, hasta 2 s, y no en el próximo I, hasta 10 s, **sin lazo al codificador**.
- La meta en una frase: gastar como un GoP largo y sufrir como un GoP corto.
- Tres métricas: cuánto dura el daño, qué tan feo se ve, y cuánto se congela. La última evita hacer trampa: congelar la imagen esconde el daño pero no lo arregla.
- La plataforma: el STM32 codifica en H.264; el edge lee la SEI y decide; SRT con pérdida controlada; el receptor mide.
- Lee la promesa.

## 12. Resultados a producir (0:50)

- Para la final reproduzco la figura 12 de AGiLE, pero en H.264: cuánta calidad se pierde según el I-header por el que se entra. AGiLE, en H.265, reporta ~1,1 puntos entrando por el primero.
- Un detalle de H.264: el I-header no puede ser un IDR, porque reiniciaría el decodificador (lo que vimos en la diapositiva 5). Tiene que ser un I normal y cada P debe mirar solo al anterior.
- Y en la plataforma comparo, con la misma pérdida: GoP largo, GoP corto, PLI y la propuesta.

## 13. Costos (0:40)

Nombra tres o cuatro, no todos:

- **Deriva**: entrar por un I-header deja un error leve hasta el próximo I.
- **Ráfaga**: un I es grande y se manda justo cuando el enlace está perdiendo.
- **Doble codificación** en el STM32.
- **Estado en el edge**: no hay lazo al codificador, pero el edge tiene que recordar a cada espectador.

## 14. Referencias (0:15)

- "Las dos principales son AGiLE y FrameTrace; el resto es la base teórica y el estándar de SRT."
- Cierra con la promesa: *"Recuperarse de la pérdida sin pedirle nada al codificador, usando un punto de recuperación que ya está en la red. Gracias, ¿preguntas?"*

---

## Preguntas probables (respuesta corta)

- **¿En qué se diferencia del refresco intra o del Recovery Point SEI?** Esos refrescan siempre y pagan siempre. Yo reutilizo algo que ya existe y solo se lo doy a quien perdió.
- **¿Por qué no basta con que SRT retransmita?** SRT retransmite mientras quede plazo. Lo que no alcanza se descarta, y esa pérdida sigue arrastrándose hasta el próximo I. Yo actúo después de eso.
- **¿Cómo sabe el edge a quién darle el I-header?** Con SRT, el emisor sabe qué paquetes descartó para cada espectador. No hace falta preguntarle al codificador.
- **¿Por qué STM32?** Un codificador embebido no puede recodificar a pedido para cada espectador; ahí el lazo cerrado no sirve y se ve el valor de la propuesta.
- **¿Por qué H.264 si AGiLE usa H.265?** El mecanismo (SEI + I no-IDR) existe en ambos, y H.264 es lo que traen los embebidos.
- **¿Por qué nadie lo hizo?** FrameTrace cita a AGiLE como técnica de video bajo demanda, cuando es de video en vivo: las dos líneas se citan sin conectarse.

## Uso de la tecnología (5 pts de la pauta)

- Presenta el **PDF** en pantalla completa. En Zoom, comparte **solo la ventana** del visor de PDF.
- Ten el guion abierto en otra pantalla o impreso.
- Antes: prueba compartir pantalla y audio, y cronométrate dos veces en voz alta.
