# Motor de decisiones financieras para autónomos y pymes — Hackathon MoraBanc

**IA + Finanzas · 7-8 noviembre 2026 · Hive Five TechLab, Andorra la Vella**

[![Verificar](https://github.com/PedroYellow/morabanc-hackathon/actions/workflows/verificar.yml/badge.svg)](https://github.com/PedroYellow/morabanc-hackathon/actions/workflows/verificar.yml)

Un motor que cruza la tesorería real de una empresa con la fiscalidad andorrana
verificada y responde a la pregunta que nadie contesta:

> **«¿Puedo permitírmelo?»**

---

## La tesis

> **La IA es el interfaz; la norma es el producto.**

El LLM **no hace aritmética**. Interpreta la pregunta en lenguaje natural,
elige qué herramienta del motor llamar, y redacta la explicación con los números
que devuelve el motor. Toda proyección, umbral de tramo, IRPF, IGI o CASS se
calcula en código determinista, con la regla aplicada citada en cada respuesta.

Eso es a la vez la garantía de correctitud y la respuesta al jurado a
*«¿cómo evitas alucinaciones numéricas?»*.

---

## Estado

| Componente | Estado | Tests |
|---|---|---|
| `engine/fiscal_andorra.py` | CASS, IRPF, IGI, crossover, simulador | **69 tests verdes** |
| `engine/tesoreria.py` | Extracto, clasificación, proyección, fugas | **57 tests verdes** |
| `engine/cierre.py` | Bucle de cierre: el motor sobre su propio consejo | **46 tests verdes** |
| `agent/bedrock_agent.py` | Bedrock Converse + tool-use (11 tools) | **69 tests verdes** |
| `lambda/handler.py` | Handler API (empaquetado y ejecutado de verdad) | **12 checks verdes** |
| `terraform/main.tf` | Infra AWS 100% IaC + publicacion del front | **`terraform validate` → Success** |
| `frontend/` | App estatica mobile-first (HTML/CSS/JS puro) | **39 asserts en Chromium real** |
| `frontend/generar_demo_data.py` | Datos demo generados por el motor real | — |
| `data/generar_demo.py` | 4 perfiles de extracto sintéticos | — |
| `normativa/generar_corpus.py` | Corpus para el RAG (5 documentos) | verificado |

**316 asserts en verde + Lambda validada + Terraform validado + front tested en navegador real.**

```
$ bash scripts/verificar.sh
  ✔ Motor fiscal andorrano — 69 asserts
  ✔ Motor de tesoreria — 57 asserts
  ✔ Bucle de cierre — 46 asserts
  ✔ Agente de Bedrock — 69 asserts
  ✔ Lambda empaquetada — 12 asserts
  ✔ Frontend — 39 asserts
  ✔ Terraform — configuracion valida
  ✔ Sintaxis JS valida
  ✔ 5 documentos normativos
  Asserts correctos: 316
  Fallos:            0
```

---

## Documentos

| Documento | Para qué |
|---|---|
| **README.md** (este) | Qué es el proyecto, la arquitectura, los hallazgos, los números |
| **DEPLOY.md** | **El día del hackathon**: comandos, roles, cronograma, plan B |

---

## Verificación

```bash
cd morabanc_hackathon

# Todo de una vez
bash scripts/verificar.sh

# O por partes
python3 tests/test_fiscal.py      # motor fiscal
python3 tests/test_tesoreria.py   # tesoreria y fugas
python3 tests/test_agente.py      # agente y contrato de herramientas
bash scripts/test_lambda.sh       # Lambda empaquetada, ejecutada
cd terraform && terraform validate # infra AWS
# Front (necesita Chromium + Playwright):
node scripts/test_frontend.js http://localhost:8899/

# Demos
python3 demo.py                    # los 5 casos del pitch (motor fiscal)
python3 demo_integrada.py         # guion completo con el agente
python3 demo_integrada.py --perfil=cierre   # el cierre del bucle de vuelta
python3 demo_integrada.py --preguntas   # modo conversacion
```

---

## Las fuentes oficiales (verificadas 23-oct-2026)

| Concepto | Fuente | Dato |
|---|---|---|
| Salari global mensual mitjà | BOPA **Decret 28/2026** (28-ene-2026) | 2.672,52 €/mes (+4,4% vs 2025) |
| Tipus de cotitzacio | Llei 11/2023 | 22% total (10% rama general + 12% jubilació) |
| Set bases CASS | CASS | 25% · 50% · 62,5% · 75% · 100% · 125% · 137,5% |
| Quotes mensuals | CASS | 146,99 · 335,57 · 367,47 · 440,97 · 587,95 · 734,94 · 808,44 € |
| Salari minim 2026 | CASS | 8,80 €/h (gen-jun) → 9,05 €/h (jul-des) |
| IRPF tipus general | Llei 5/2014 (consolidada Llei 5/2025), art. 43 | 10% |
| Minim personal exempt | art. 35 | 24.000 € (30.000 € si incapacitated) |
| Bonificació activitats | art. 46 | 50% del 10% sobre base reduïda, **tope 800 €** |
| Minim exempt estalvi | art. 37 | 3.000 € |
| IGI | Impost sobre activitats econòmiques | 4,5% |
| Pagament fraccionat | Reglament IRPF, art. 5 | 5% de rendes netes |

### Detalles finos que los tests Discovering (y que nadie publica)

- La base del **50%** no és el 50% matemàtic de 2.672,52 € (donaria 1.336,26 €).
  És el **salari mínim** (1.525,33 € al S1 de 2026), que puja automàticament a
  1.568,67 € des de l'1 de juliol de 2026.
- La base del **62,5%** oficial és 1.670,33 €, que surt del 62,5% d'un salari
  global **sense truncar**. Per això el motor usa la taula publicada com a font
  de veritat en lloc de recalcular.
- Els trams **< 100% són opcionals** (cal sol·licitar-los); els **≥ 100% són
  obligatoris** quan es compleixen les condicions.
- La **suma de les ramas arrodonides** pot diferir 0,01 € de la quota oficial
  publicada (p. ex. 125%: 334,07 + 400,88 = 734,95 vs 734,94 oficial).

---

## El hallazgo de mercat: el "5%" no és real

Tothom publica que l'IRPF andorrà és `0% / 5% / 10%`. És una **simplificació
de màrqueting** i és falsa.

El càlcul real de la bonificació de l'art. 46 (50% sobre el 10%, tope 800 €):

| Base general | Quota IRPF | Bonificació | Tipus efectiu real |
|---|---|---|---|
| 24.000 € | 0 € | 0 € | 0,00% |
| 26.000 € | 100 € | 100 € | **0,38%** |
| 30.000 € | 300 € | 300 € | 1,00% |
| 35.000 € | 550 € | 550 € | 1,57% |
| 40.000 € | 800 € | **800 € (tope)** | 2,00% |
| 45.000 € | 1.300 € | 800 € | 2,89% |

**El tope de 800 € s'assoleix exactament a 40.000 € de base.** Aquest és el punt
on la bonificació es congela, l'IRPF accelera i la CASS salta del 100% al 125%.

Un ERP comptable no mostra aquest matís. És l'argument que aquí hi ha un motor,
no un chatbot.

---

## El crossover de la CASS

La CASS és un cost **fix per tram** que no escala amb la renda. Per això augmentar
els ingressos pot deixar de compensar:

| Renda neta | Tramo CASS | Quota/mes | Delta anual |
|---|---|---|---|
| 30.000 € | 100% | 587,95 € | — |
| 45.000 € | 125% | 734,94 € | **+1.763,88 €** |
| 55.000 € | 137,5% | 808,44 € | **+882,00 €** |

A 45.000 € el salt de tramo suma **1.763,88 €/any** a la CASS, i l'IRPF efectiu
també puja del 5% al 10%. Això és el que fa que «facturar més» no sigui sempre
millor, i és el que cap ERP de comptabilitat explica.

---

## Números reals del caso de demo

**Freelance a 30.000 €/any**
- CASS 100% → 587,95 €/mes (267,25 general + 320,70 jubilació) → **7.055,40 €/any**
- IRPF: base 6.000 € → quota 600 € − bonificació 300 € = **300 €** (efectiu 1,00%)
- Carga fiscal total: **7.355,40 € (24,52%)** → net real 22.644,60 €

**Contratar a 2.400 €/mes**
- Cost: **28.800 €/any**
- Facturació extra necessària: **42.994,29 €** (61.420,41 € bruts al 70% de marge)
- D'aquests, **1.851,43 €** són IGI
- La renda neta no canvia (el cost és despesa deduïble): el que canvia és la **caixa**

**Freelancer amb nòmina (el cas del pitch)**
- Flux net: **−4.267,05 €/any**
- 5 fugas detectades: **192,79 €/mes recuperables** (2.313,48 €/any)
- La caixa s'agota al **mes 9**

---

## Arquitectura

```
┌─ FRONT (CloudFront + S3) ──────────────────────────────────┐
│  1-2 pantallas, mobile-first, ES + CA + EN                   │
│  Sube extracto (CSV) o cuenta demo precargada                │
└────────────────────────┬───────────────────────────────────┘
                         │ API Gateway HTTP
┌────────────────────────▼───────────────────────────────────┐
│  Lambda API ── valida, carga contexto, llama al agente     │
└────────────────────────┬───────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────┐
│  AGENTE (Bedrock Converse + tool-use, Nova Pro)             │
│  11 tools · RAG sobre normativa andorrana · Guardrails      │
│  ✔ NUNCA calcula: elige tool, redacta, cita la regla        │
└────────────────────────┬───────────────────────────────────┘
                         │ tool calls
┌────────────────────────▼───────────────────────────────────┐
│  MOTOR DETERMINISTA (Lambda, Python)  ◄── EL CEREBRO         │
│  engine/fiscal_andorra.py  CASS · IRPF · IGI · crossover    │
│  engine/tesoreria.py       extracto · proyección · fugas    │
│  Persistencia: DynamoDB (TTL 30d) + S3 (cifrado KMS)        │
└─────────────────────────────────────────────────────────────┘
```

### Las 11 herramientas del agente

`analizar_tesoreria` · `detectar_fugas` · `proyectar_caja` · `tramo_cass` ·
`calcular_irpf` · `calcular_igi` · `detectar_crossover_fiscal` ·
`simular_contratacion` · `punto_optimo_facturacion` · `comparar_escenarios` ·
`cerrar_ciclo`

### El bucle de cierre

La undécima herramienta es la que separa un prototipo de un producto:
**el sistema se reporta sobre su propio consejo pasado**.

Cuando el motor detecta una fuga («cancela esta suscripción de 12,99 €/mes»),
ese consejo es una hipótesis sobre el futuro. `engine/cierre.py` la guarda y,
cuando llegan movimientos nuevos, la comprueba contra los hechos:

| Veredicto | Qué significa |
|---|---|
| `cumplido` | El cargo desapareció. Ahorro = importe previsto. |
| `parcial` | El cargo sigue pero a otro precio (subió). Ahorro parcial. |
| `incumplido` | El cargo sigue igual. Ahorro 0. |
| `sin_datos` | No hay movimientos suficientes todavía. **No se inventa.** |

El perfil de demo `demo_freelancer_cierre.csv` cuenta la historia completa:
4 suscripciones, el motor avisa el 1 de julio de 2026, el autónomo cancela
2 y mantiene 2. Al corte:

> *Has seguido 2 de 4 recomendaciones. Llevas ahorrados 23,98 €/mes de los
> 103,96 €/mes previstos.*

Es el momento del pitch que ni un ERP ni un chatbot pueden enseñar.

---

## El frontend

App **estática** (HTML + CSS + JS puro, sin build step, sin dependencias) que se
publica en S3 y se sirve por CloudFront. Mobile-first, 3 idiomas (ES/CA/EN).

**Regla del proyecto: el JavaScript no calcula nada.** Solo pide, muestra y dibuja.

- **Modo real**: llama a la API en AWS (`/__API_URL__`), el agente de Bedrock elige
  las herramientas y el motor calcula.
- **Modo demo**: consume `data/demo_data.json`, que genera
  `frontend/generar_demo_data.py` ejecutando el **mismo motor de Python** que corre
  en AWS. Por eso los números son idénticos en ambos modos y no hay lógica
  duplicada en JS.

### Pantallas

1. **Contexto** — 4 cuentas de demostración + subida de extracto CSV (procesado en
   el navegador) + 4 campos fiscales.
2. **Resultado** — veredicto con la acción, 4 métricas, hallazgos (el crossover de
   IRPF destacado en amarillo), gráfico SVG de caja mes a mes (verde hasta el
   quiebre, rojo después), chat con el agente, y la traza técnica con las reglas
   aplicadas (para el jurado técnico).

### Detalles de implementation

- Iconos **SVG inline**, no emojis: los emojis no renderizan en muchos sistemas.
- El gráfico calcula la escala de la fuente segun el ancho real del SVG, para que
  las cifras del eje sean legibles en movil (304px) como en escritorio (780px).
- `[hidden] { display: none !important; }` — sin esta regla, el fondo del modal
  (`display:flex`) intercepta todos los clics aunque tenga `hidden`.

---

## El corpus normativo (RAG)

`normativa/generar_corpus.py` genera 5 documentos con la normativa verificada,
listos para que los ingiera el data source de Bedrock:

1. **CASS** — base, 7 tramos, cuotas, reglas de opcionalidad
2. **IRPF** — arts. 35, 37, 43 y 46, con la tabla del tipo efectivo real
3. **IGI** — 4,5%, gastos deducibles, pago fraccionado
4. **IRNR** — frontereros y temporeros, reforma de nov-2025
5. **Guía de simulación** — las preguntas frecuentes de los autónomos

El documento 2 incluye la **tabla completa del tipo efectivo real** (0,38% a
26.000€, 1,00% a 30.000€, 2,00% a 40.000€), que es lo que el RAG cita cuando
alguien pregunta por el IRPF. Así el corpus y el motor dicen exactamente lo
mismo: si discrepan, es un bug.

```bash
python3 normativa/generar_corpus.py   # regenera los .md
```

---

## Terraform (requisito de descalificación)

Base tècnica de MoraBanc, clàusula quarta: *«Tota la infraestructura AWS […]
haurà de estar definida íntegrament mitjançant Terraform»*.

`terraform/main.tf` defineix, sense un sol recurs creat a mà:

- **KMS** (cifrat de dades, rotació de clau)
- **S3** (extractes + corpus normatiu, SSE-KMS, bloqueig de publica, lifecycle 90d)
- **DynamoDB** (TTL 30 dies, PITR, xifrat)
- **Lambda** ×2 (API + motor), Python 3.13, X-Ray
- **API Gateway** HTTP API amb CORS
- **CloudFront** + OAC (front estàtic, signat)
- **Cognito** (auth, MFA, revocació de token)
- **Bedrock Guardrails** (PII, prompt injection, secrets)
- **Bedrock Knowledge Base** + OpenSearch Serverless (RAG de la normativa)
- **SNS + CloudWatch** (alarmes)
- **IAM** de mínim privilegi per funció

```bash
cd terraform
terraform init
terraform validate   # → Success! The configuration is valid.
terraform plan
```

El paquete de la Lambda (`archive_file "motor"`) lleva solo lo que hace falta
en runtime — `engine/`, `agent/`, `lambda/` — y excluye front, scripts, tests
y demos. Son 40 KB en vez de 76 KB, y el cold start mejora.

El `handler` de las dos Lambdas es **`lambda.handler.lambda_handler`**, que
coincide con la estructura del zip. `scripts/test_lambda.sh` importa el módulo
**exactamente como lo hace AWS** y comprueba que el path de Terraform coincide,
así que un desajuste se detecta en local y no en la primera invocación del día 7.

---

## Seguridad (argumento de pitch)

- Tout viu a la **cuenta AWS aislada de l'equip**, xifrat amb KMS.
- IAM de mínim privilegi: el rol de la Lambda només pot cridar al model concret.
- **Bedrock Guardrails** anonimitza PII i bloqueja secrets i prompt injection.
- Sense *training* sobre dades del client. La IA processa, no emmagatzema.
- **TTL de 30 dies** a DynamoDB: les dades del client s'esborren soles.
- El guardrail s'activa a l'IAM de la Lambda, no és decoratiu.

---

## Pendiente

- [x] Frontend (1-2 pantallas, mobile-first, ES + CA + EN)
- [x] Corpus normatiu a S3 (`normativa/`) per al RAG
- [x] Bucle de cierre: el sistema reporta sobre su propio consejo pasado
      (`engine/cierre.py`, 46 tests, tool `cerrar_ciclo`, perfil de demo)
- [x] Repositori propi amb CI (GitHub Actions) i script de sincronitzacio
      al GitLab de MoraBanc (`scripts/sync_gitlab.sh`)
- [ ] Knowledge Base real (la infra y el corpus estan; falta el apply con credenciales)
- [ ] Probar con credenciales AWS reales (session Bedrock + KB)
- [ ] GitLab de MoraBanc + cuenta AWS del equipo

---

## GitLab de MoraBanc (requisito de descalificación)

Las bases obligan a subir el codigo al **GitLab.com** del proyecto que crea
MoraBanc. Este repositorio es el **maestro de trabajo** y se sincroniza al
GitLab oficial:

- GitLab (oficial del hackathon): https://gitlab.com/pedro322/morabanc-hackathon
- GitHub (maestro): https://github.com/PedroYellow/morabanc-hackathon

```bash
bash scripts/push_gitlab.sh      # publica en GitLab (verifica la suite antes)
```

El script **verifica la suite antes de publicar**: si algo esta roto, no
publica. Si el push falla con 403, es que el token no tiene el permiso
`Code: Push` — la solucion esta en `DEPLOY.md` (seccion "Si el push a GitLab
falla con 403").

> El token de GitLab expira. Revocalo en cuanto entregues. Si expira durante
> el pitch, GitHub sigue siendo el maestro y el modo demo local funciona sin
> AWS.
