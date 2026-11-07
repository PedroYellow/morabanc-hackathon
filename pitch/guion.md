# MoraBanc Asesor — 100s de autobpresentacion

Estilo UbotPay: el producto se presenta en primera persona. El motor es
la voz. Las slides son apoyo visual; la web real es la protagonista.

**Voz:** la del propio producto (ElevenLabs) cuando haya saldo; mientras
tanto, Edge TTS con el mismo guion.

---

## S1 · Apertura (0:00-0:12) · slide d01

> Hola. Soy el asesor financiero de MoraBanc. Me可供 built en dos días.
> Te voy a enseñar cómo trabajo.

O en español natural, que es lo que quieres:

> Hola. Soy el asesor financiero de MoraBanc. Pedro me ha construido en
> dos días. Déjame enseñarte cómo trabajo.

## S2 · El problema (0:12-0:24) · slide d02

> Todo el mundo te dice que el IRPF andorrà es cero, cinco o diez por
> ciento. Es una simplificación de marketing. Y es falsa.
>
> Porque la bonificación real es la mitad del diez por ciento, con un tope
> de ochocientos euros. Y ese tope se alcanza exactamente en cuarenta mil
> euros de base.

## S3 · Lo que yo veo (0:24-0:36) · slide d03

> Mira esta tabla. Con treinta mil euros de base, tu tipo efectivo es del
> uno por ciento. No del cinco.
>
> Y en cuanto pasas de cuarenta mil, el tope se congela, el IRPF acelera, y
> la CASS salta del cien al ciento veinticinco por ciento. Un ERP contable
> no te enseña este matiz.

## S4 · Cómo me usas (0:36-0:50) · slide d04

> Así se usa. Tres pasos.
>
> Uno: subes el extracto de tu banco. Es un CSV, no un formulario.
> Dos: yo calculo. IRPF, IGI, CASS, tesorería, las fugas de gasto.
> Tres: te lo explico con la regla aplicada, el artículo de la ley, el
> tramo, el cálculo.

## S5 · Mi garantía (0:50-1:04) · slide d07

> Y esto es lo más importante de todo.
>
> Yo no hago aritmética. El modelo elige qué herramienta del motor llamar y
> redacta la respuesta. Cada cifra sale de código determinista.
>
> No es que yo sea preciso. Es que no puedo inventarme un número.

## S6 · Me evalúo (1:04-1:16) · slide d08

> Y hay una cosa más que no tiene nadie. Me evalúo a mí mismo.
>
> Te doy un consejo en enero, guardo la fecha, y en junio vuelvo a mirar si
> lo cumpliste. Este freelance siguió dos de cuatro. Y ahorró veintitrés
> euros y noventa y ocho al mes.

## S7 · La demo (1:16-1:32) · web real

> Mira. Este es el caso de verdad.
>
> Treinta mil euros de ingresos. Detecto que su caja se agota en el mes
> nueve, y le digo exactamente por qué. La bonificación se congela en
> cuarenta mil, la CASS salta al ciento veinticinco, y con eso el flujo se
> va a menos cuatro mil doscientos sesenta y siete al mes.
>
> Cuatrocientas treinta y siete. Hmm. Cuatro mil doscientos sesenta y siete
> al mes.

## S8 · Cierre (1:32-1:44) · slide d12

> Soy el asesor financiero de MoraBanc. La inteligencia artificial es el
> interfaz. La norma es el producto.
>
> Porque un asesor fiscal no debería estar explicándote porcentajes.
> Debería explicarte decisiones.
>
> Pruébalo en welcomeandorra punto com.

---

## Guia de uso (la "pequeña guia del agente")

Va dentro del video como una slide propia, d13, y tambien como el
README del repo. Es lo que el jurado pregunta: "vale, y como se usa?".

### Como preguntarme

Escribe en lenguaje natural. Yo traduzco a la herramienta correcta.

| Pregunta | Que hago |
|----------|----------|
| "Cuanto pago de IRPF con 30.000 €" | Tramo de IRPF + bonificacion del art. 46 |
| "De quanto es mi CASS este año" | Base de la CASS y tipo efectivo |
| "Que fugas de gasto tengo" | Analisis del extracto: suscripciones, signos, etc. |
| "Cuando se me acaba la caja" | Proyeccion de tesoreria y mes de quiebre |
| "Y si subo a 40.000 €" | Recalculo completo con la nueva renta |
| "Cumpli mis consejos?" | Informe de cierre: seguimiento mes a mes |

### Que necesito de ti

- El extracto del banco en CSV (o el fichero de demo, si solo quieres ver
  como funciona).
- Tu actividad y tus ingresos, en el formulario.

### Que te devuelvo

Siempre tres cosas: **la cifra**, **la regla que la produce** y **que
deberias hacer**. Nunca solo el numero.

---

## Notas de produccion

- Tono: primera persona, como si el producto hablara. Frases cortas.
- Las slides son apoyo, no el protagonista: la web real es el momento clave.
- Numeros en palabras para el TTS. En pantalla, formato europeo.
- Subtitulos: 2 lineas maximo, 50 px, sin tapar el pie.
