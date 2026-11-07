# Pitch y preguntas del jurado — MoraBanc

> Documento de trabajo para el ensayo. Cada respuesta tiene el numero
> **saliente de la regla** que lo sostiene: eso es lo que hace que el
> jurado confie en vez de pedir una demo.

---

## 1. Las 4 frases del pitch (30 segundos)

1. **"La IA es el interfaz. La norma es el producto."**
   El LLM elige la herramienta y redacta. Cada numero sale de codigo
   determinista en Python, con la regla legal que lo origina.

2. **"No alucinamos cifras: las calculamos y las auditamos."**
   Motor determinista, una linea de codigo por regla, tests de
   regresion, y la cita legal en cada respuesta.

3. **"La evidencia: el motor se reporta sobre sus propios consejos."**
   Bucle de cierre: el motor dice "cancela Netflix", tres meses despues
   se reevalua y dice si lo has hecho. El motor se audita a si mismo.

4. **"Andorra, no un ejemplo generico."**
   CASS por tramos, IRPF con bonificacion art. 46, IGI, y el detalle
   de que el tramo de CASS lo fija el ingreso del ANIO ANTERIOR.

---

## 2. La demo (5 minutos)

| Momento | Que se ve | Que hay que decir |
|---------|-----------|------------------|
| 0:00 | Home con los 4 perfiles | "Cargad un extracto real de 12 meses." |
| 0:30 | Resultado: CASS 587,95 €/mes, flujo -4.267,05 €/ano, mes 9 | "El motor ha leido 236 movimientos." |
| 1:30 | Las 4 fugas con su ahorro | "1.066 €/ano de Adobe. 12 cobros en 12 meses." |
| 2:30 | Modo presentacion | "Un solo pantallazo para el consejo de administracion." |
| 3:30 | Pregunta en el chat | "Preguntale lo que quieras. La respuesta cita la regla." |
| 4:30 | Bucle de cierre | "Y el motor se evalua a si mismo tres meses despues." |

---

## 3. Preguntas del jurado (con la respuesta y la regla)

### "¿Como evitas que la IA se invente los numeros?"
El LLM **nunca** calcula. Elige una de las 11 herramientas del motor y
redacta la respuesta con el resultado que le devuelve ese codigo. La
respuesta lleva siempre el campo "regla" con la cita legal. Si el motor
no sabe, lo dice.

Prueba en vivo: se cambian los numeros del motor y la respuesta cambia.
No se puede hacer eso con un LLM.

### "¿Que pasa si la normativa cambia?"
La normativa esta en un corpus versionado (`normativa/`) con su indice.
El motor cita el articulo. Cambiar la norma es cambiar un dato, no
reentrenar un modelo. La base de conocimiento (Bedrock Knowledge Base)
recupera el texto vigente, pero **el calculo sigue siendo codigo**.

### "¿El modelo no alucina las reglas?"
No las genera: las cita. Cada calculo sale con un campo `regla` que
apunta al articulo (p.ej. "CASS 100%. Base global 2.672,52 EUR (Decret
28/2026)"). En la demo puedes abrir la traza tecnica y ver la fuente.

### "¿Por que un motor propio y no un LLM con RAG?"
Porque un RAG te da el texto, no el calculo. El IRPF con bonificacion
art. 46 (50% con tope de 800 EUR) y la progresividad 0%-2% entre 24.000 y
40.000 EUR son reglas con estado: no se leen, se calculan. Un LLM que
calcula te da un numero plausible y falso, que es peor que no dar
numero.

### "¿Que pasa al cruzar los 40.000 EUR de renta?"
Aqui esta el detalle que demuestra que el motor es el producto: **el
tramo de CASS lo fija el ingreso del AÑO ANTERIOR**, que se declara en
enero. Cruzar los 40.000 **no** te sube la cuota de este ano: te sube la
del ano que viene. +1.763,88 EUR/ano. Un LLM responderia "te sube ahora"
y estaria mal.

### "¿Como gestionais el aislamiento entre clientes?"
Cada peticion lleva su contexto (`ContextoEmpresa`) y el motor es una
funcion pura: entra el contexto, sale el resultado. Sin estado global.
El modelo solo ve lo que se le pasa en el prompt. Y `/preguntar` esta
protegido por API key + Lambda authorizer, con la cuota de Bedrock
acotada.

### "¿Y los datos personales?"
El extracto se procesa en memoria. El unico dato que se guarda es el
perfil de demo, y es sintetico (generado por el motor, no son datos de
una persona real).

### "¿Cuanto cuesta?"
El coste variable es Bedrock (una llamada por pregunta) y el resto es
estatico. Por eso la API key controla la cuota: es un limite de gasto,
no un muro.

### "¿Como se despliega?"
Terraform completo: API Gateway, 3 Lambdas (motor, API, authorizer),
Cognito, DynamoDB, S3, CloudFront, OpenSearch Serverless, Bedrock
Knowledge Base. `terraform apply` y el front se publica solo. CI con
GitHub Actions. Todo en `us-east-1` (la cuenta del workshop no permite
crear en otras regiones).

---

## 4. Las trampas (lo que NO hay que decir)

- **No digas "es una calculadora"**: di "es un motor de decision con
  interfaz conversacional".
- **No digas que la IA "aprende"**: no hay entrenamiento. Hay un motor
  con las reglas y un LLM que redacta.
- **No prometas mas de lo que hay**: la demo en vivo usa el motor; el
  RAG (base de conocimiento) es opcional y puede no estar desplegado.
- **Si no sabes algo, dilo**: "no lo tengo delante, pero el motor cita la
  regla, puedo enseñartela".
- **El "5%" del IRPF**: es una simplificacion publicada. El tipo real
  sube del 0% al 2% de forma progresiva entre 24.000 y 40.000 EUR. Si
  te lo preguntan, ESO es lo que demuestra que el motor va mas alla del
  titular.

---

## 5. Cronometro del ensayo

| Bloque | Tiempo | Objetivo |
|--------|--------|----------|
| Apertura | 0:00 - 0:30 | la frase gancho + a quien va dirigido |
| Problema | 0:30 - 1:30 | un autonomo andorran con 30.000 EUR: ni la web ni el gestor le dicen lo que va a pasar |
| Demo | 1:30 - 4:30 | el flujo de 5 pasos, sin correr |
| Cierre | 4:30 - 5:00 | que se recuerda: "la IA es el interfaz, la norma es el producto" |

Total: **5 minutos**. Si sobra tiempo, la pregunta de los 40.000 EUR.

---

## 6. Pregunta para los organizadores (enviar por escrito)

> **Asunto**: repo de GitLab del hackathon
>
> Hola, equipo del hackathon:
>
> Hemos publicado nuestro proyecto en **https://gitlab.com/pedro322/morabanc-hackathon**
> (publico, rama `main`), que es el repositorio que nos creasteis a
> nosotros.
>
> Una duda: **¿ese es el espacio que esperais que usemos**, o hay un
> grupo/proyecto comun del hackathon donde deberia estar el codigo para
> que lo vea el resto de equipos y el jurado?
>
> Si es lo segundo, ¿donde exactamente? Podemos moverlo o hacer un
> fork, lo que os sea mas comodo.
>
> Gracias!

