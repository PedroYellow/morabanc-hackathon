# Despliegue — Hackathon MoraBanc IA + Finanzas

**7-8 noviembre 2026 · Hive Five TechLab, Andorra la Vella**

Este documento es para el día del hackathon. Está escrito asumiendo que llegas
a las 08:30 con 15 días de trabajo ya hecho y 1 día y medio por delante.

Si algo aquí no coincide con lo que ves en el repo, **manda el repo**: este
documento se actualizó por última vez el 24 de octubre de 2026.

---

## TL;DR — Los 4 comandos del día 7

```bash
# 1. Instalar Terraform (si no lo tienes)
#    https://developer.hashicorp.com/terraform/downloads

# 2. Credenciales de AWS que da MoraBanc
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...      # si es sesion temporal
export AWS_DEFAULT_REGION=eu-west-1

# 3. Desplegar TODA la infraestructura (init + validate + plan + apply
#    con reintentos) y publicar el front con la config real
bash scripts/deploy_infra.sh

# 4. Comprobar que Bedrock responde de verdad (no en mock)
python3 scripts/test_bedrock_live.py
```

Los pasos 3 y 4 cubren: la infra, el front publicado y el agente contra
Bedrock real (11 herramientas y el número de la respuesta contrastado con el
del motor).

Si algo falla, **no sigas adelante**: hay un "Plan B" al final de este
documento (§8) que te da una demo funcional sin AWS.

> **El código ya está en los dos repos** (GitHub maestro y GitLab de
> MoraBanc). Si se os cae la red, el modo demo local funciona sin AWS.

---

## 1. Estado del proyecto al llegar

| Pieza | Estado | Verificación |
|---|---|---|
| Motor fiscal andorrano (CASS, IRPF, IGI, crossover) | **Listo** | 69 tests contra valores oficiales |
| Motor de tesorería (extracto, proyección, fugas) | **Listo** | 57 tests |
| Agente Bedrock con tool-use (11 herramientas) | **Escrito, probado en mock** | 69 tests |
| Bucle de cierre (el motor sobre su propio consejo) | **Listo** | 46 tests |
| Lambda (handler API) | **Listo** | 8 checks, empaquetada y ejecutada |
| Frontend (estático, ES/CA/EN) | **Listo** | 38 asserts en Chromium real |
| Terraform (infra AWS 100% IaC) | **Validado** | `terraform validate` → Success |
| Corpus normativo para el RAG (5 docs) | **Listo** | Cifras clave verificadas |
| Front servido desde CloudFront con API real | **Pendiente** | Requiere `terraform apply` |

**434 asserts en verde.** Verificación completa en un comando:

```bash
bash scripts/verificar.sh
```

> **Nota sobre el agente**: la integración con Bedrock usa la Converse API real
> (`toolConfig` / `toolUse` / `toolResult`, modelo `amazon.nova-pro-v1:0`). Está
> escrita contra la documentación de AWS, pero **solo se ha ejecutado en modo
> mock** — falta probarla con credenciales reales. Es el primer thing-to-do del
> día 7 (§4, paso 2).

---

## 2. Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Python | 3.11+ | motor, tests, generadores (no hace falta nada más instalado) |
| Terraform | >= 1.5 | la infra (requisito de las bases) |
| AWS CLI | v2 | credenciales y S3 |
| Node | 18+ | **solo** para el test end-to-end del front (opcional) |

No hay `pip install`. El motor usa solo la biblioteca estándar: `Decimal`,
`dataclasses`, `csv`, `re`. **Cero dependencias** — eso también es un argumento
para el jurado (nada que instalar en el portátil del evaluador).

---

## 3. Reparto de roles

Tres personas, tres responsabilidades. **El frontend no calcula nada**, así que
quien lo hace no necesita tocar el motor.

### Persona 1 — Motor y backend
- Motor fiscal y tesorería (ya hecho, verificado)
- Lambda, IAM, Terraform
- Conectar el agente con Bedrock en vivo
- **Dueño del `terraform apply`**

### Persona 2 — Frontend y demo
- Front, textos, i18n, capturas
- Guion del pitch y ensayo
- **Dueño del cronómetro en el pitch**

### Persona 3 — Producto y fiscalidad
- Validar los importes con la normativa (usar el corpus de `normativa/`)
- Preparar las respuestas al jurado
- Contacto con MoraBanc si hace falta (credenciales, GitLab)
- **Dueño de "eso no lo sé, lo consulto"** — que es una respuesta legítima

**Si sois menos de 3:** la Persona 3 puede ser un perfil de negocio sin código
(hackingathon de equipos multidisciplinares, explícitamente incentivado). Que
alguien valide la fiscalidad vale más que un cuarto programador.

---

## 4. El día 7 (7 de noviembre) — hora a hora

### 08:30 — Llegada

```bash
cd morabanc_hackathon
bash scripts/verificar.sh        # que todo sigue verde
```

Si algo falla, **para todo el equipo y arregladlo**. Con 434 asserts en verde,
un fallo significa que alguien cambió algo.

### 09:00 — Credenciales

Lo primero que se pide a MoraBanc (tel. **+376 884 884**):
1. **Credenciales AWS de la cuenta del equipo** → permite `terraform apply`
2. **Acceso al proyecto de GitLab** → las bases obligan a subir el código allí
3. **Modelos Bedrock habilitados** en la cuenta (puede que haya que pedirlo)

> **Sobre GitLab**: las bases dicen que el código debe ir al espacio que crea
> MoraBanc. Si el acceso no llega el día 7, **preguntadlo a primera hora**: es un
> requisito de descalificación, no un detalle.

### 09:30 — Desplegar la infraestructura (Persona 1)

```bash
bash scripts/deploy_infra.sh
```

Un comando hace todo: comprueba credenciales → `init` → `validate` → `plan`
→ `apply` **con 3 reintentos** → verifica que la API responde → publica el
front con la config real.

Los reintentos no son paranoia: la primera vez, la colección de OpenSearch
tarda 1-2 minutos en estar lista y el IAM tarda en propagarse. Sin reintentos,
eso es un `apply` fallido a mitad con la infra a medias y sin tiempo para
arreglarlo.

Si solo quieres ver qué se va a crear **sin crear nada**:

```bash
bash scripts/deploy_infra.sh --plan-only
```

Qué crea (todo en 4-6 minutos):

| Recurso | Para qué |
|---|---|
| KMS key | cifrado de datos en reposo, rotación activada |
| S3 bucket | extractos + corpus normativo + front estático, SSE-KMS, sin acceso público |
| DynamoDB | movimientos y escenarios, TTL 30 días, PITR |
| Lambda ×2 | API + motor, Python 3.13, X-Ray |
| API Gateway | HTTP API con CORS |
| CloudFront | front estático (TTL 60s) + origen de API sin caché |
| Cognito | user pool, MFA opcional, revocación de token |
| Bedrock Guardrails | PII anonimizada, secrets bloqueados, prompt injection |
| Bedrock Knowledge Base | RAG con el corpus normativo |
| OpenSearch Serverless | almacén vectorial de la KB |
| SNS + CloudWatch | alarma de errores en la Lambda |
| IAM | un rol por función, mínimo privilegio |

**Salidas que importan:**

```bash
terraform output                 # api_url, front_url, cognito_*, bucket_datos, guardrail_id
terraform output -json frontend_url_config
```

> **Si el apply falla 3 veces**, no sigas reintentando a mano: ve al §8 (Plan
> B). El modo demo local funciona sin AWS y es una demo legítima. Un
> prototipo local que funciona y explica el insight fiscal gana a un
> prototipo en AWS que no llega a tiempo.

### 10:00 — Probar Bedrock en vivo (Persona 1) ← **lo más crítico**

Esto es lo que no está verificado. El agente está escrito contra la API real
pero solo se ha ejecutado en mock.

```bash
export AWS_PROFILE=morabanc
python3 - <<'PY'
import sys, os
sys.path.insert(0, ".")
from agent.bedrock_agent import AgenteFinanciero, ContextoEmpresa
from decimal import Decimal as D

ctx = ContextoEmpresa(
    movimientos=[],
    saldo_actual=D("8500"),
    renta_neta_anual=D("30000"),
    margen_bruto=D("0.70"),
)
ag = AgenteFinanciero(ctx, mock=False)      # <-- modo real
r = ag.preguntar("¿Cuánto cotizo a la CASS?")
print(r["respuesta"])
print("herramientas:", [h["tool"] for h in r["herramientas"]])
PY
```

**Si da error**, lo más probable es:

| Error | Causa | Solución |
|---|---|---|
| `AccessDeniedException` | modelo no habilitado en la cuenta | pedir a AWS que habilite `amazon.nova-pro-v1:0` |
| `ValidationException` | el modelo no soporta tool-use | cambiar a `anthropic.claude-3-5-sonnet-20241022-v2:0` en `MODEL_ID` |
| `ResourceNotFound` | `BEDROCK_MODEL_ID` mal escrito | mirar `aws bedrock list-foundation-models --region eu-west-1` |
| Timeout | el bucle de tools no converge | bajar `MAX_ITERACIONES` y revisar la traza |

Fallback: si Bedrock no se puede habilitar, el **modo mock** funciona y la demo
no se rompe. No es lo ideal (el jurado quiere ver IA real), pero es un plan B
viable.

### 11:00 — Publicar el front (Persona 2)

```bash
bash scripts/deploy_front.sh
```

El script regenera los datos demo con el motor real, inyecta `__API_URL__` en
`index.html` y publica a S3.

> **Modo demo vs modo real**: sin `terraform apply`, el front funciona en
> **modo demo** — consume `data/demo_data.json`, que genera el mismo motor
> Python. Los números son idénticos. Es un fallback legítimo para ensayar.

### 12:00 — Knowledge Base

El data source tarda **5-15 minutos** en indexar el corpus. Verifica:

```bash
aws bedrock-agent list-data-sources --region eu-west-1
aws bedrock-agent list-knowledge-bases --region eu-west-1
```

Cuando termine, prueba el RAG:

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, ".")
from agent.bedrock_agent import AgenteFinanciero, ContextoEmpresa
from decimal import Decimal as D
ctx = ContextoEmpresa(renta_neta_anual=D("26000"))
ag = AgenteFinanciero(ctx, mock=False)
print(ag.preguntar("¿Por qué el IRPF no es 5%?")["respuesta"])
PY
```

Si el RAG no está listo a tiempo, **no es bloqueante**: el motor ya tiene la
normativa codificada y responde igual. El RAG es el extra.

### 13:00 — Fin de la mañana

Deberías tener:
- [ ] Infra desplegada, `terraform output` con URLs
- [ ] Bedrock respondiendo en vivo
- [ ] Front publicado y sirviendo desde CloudFront
- [ ] El pitch funcionando de punta a punta

**Si faltan cosas, prioriza así:**
1. Bedrock en vivo (sin esto no hay IA)
2. Front publicado (sin esto no hay demo)
3. Knowledge Base (nice-to-have)

### 14:00 — 17:00 — Pulido y ensayo

- Grabar el pitch 3 veces seguidas. La tercera tiene que salir sin mirar notas.
- **Que alguien del equipo que NO ha tribalizado el proyecto lo vea.** Si no
  entiende la demo en 6 minutos, es que la demo está mal.
- Preparar las respuestas al jurado (§6).
- Backups: tener el pitch en PDF y en capturas por si el wifi falla.

### 18:00 — Cierre del día 1

- Subir todo al GitLab de MoraBanc. **Es un requisito de las bases.**
  ```bash
  GITLAB_REMOTE=https://gitlab.com/pedro322/morabanc-hackathon.git \
    bash scripts/sync_gitlab.sh
  ```
  El script verifica la suite antes de publicar: si algo está roto, no publica.
- Dejar el repo en un estado que alguien pueda retomar en 5 minutos.
- No tocar el motor después de las 18:00 salvo que algo esté roto.

#### Si el push a GitLab falla con 403

Es el fallo mas probable del día, y no es del código: es **un token de GitLab
sin permiso de escritura**.

GitLab distingue dos tipos de token:

| Tipo | Permiso | Nota |
|---|---|---|
| **Classic** (`glpat-...`) | `write_repository` | Funciona tal cual para push. |
| **Fine-grained** | Hay que elegir el rol por proyecto | Sin el rol adecuado, da 403 aunque tu usuario sea Owner del proyecto. |

El error lo dice exactamente:

```
remote: Access denied: This operation requires a fine-grained personal
access token with the following project permissions: [Code: Push].
```

**La solucion (30 segundos, en el navegador):**

1. GitLab → **Edit profile** → **Access Tokens** → **Add new token**
2. Scope: `write_repository` (classic) — o, si es fine-grained, elige el
   proyecto `morabanc-hackathon` con rol **Maintainer** y marca **Code: Push**
3. Copia el token y exportalo:

```bash
export GITLAB_TOKEN="glpat-..."
printf 'https://pedro322:%s@gitlab.com\n' "$GITLAB_TOKEN" \
  > ~/.git-credentials-gitlab
chmod 600 ~/.git-credentials-gitlab
git config credential.helper "store --file=$HOME/.git-credentials-gitlab"
git remote set-url gitlab https://gitlab.com/pedro322/morabanc-hackathon.git
git push gitlab main
```

**No pongas el token en la URL del remote ni en ningun fichero del repo.**
El fichero de credenciales va en tu home, con permisos 600, y esta fuera del
repo. Comprobado: `git grep glpat-` no encuentra nada ni en el codigo ni en
el historial.

> **El token expira.** Revocalo en cuanto entregues (GitLab → Access Tokens →
> Revoke). Si expira durante el pitch, el repo de GitHub sigue siendo el
> maestro y `bash scripts/sync_gitlab.sh` vuelve a publicar en un minuto.

---

## 5. El día 8 (8 de noviembre) — el pitch

### 08:30 — Desayuno y repaso

Repasar el guion (§5 del README principal) una vez. Sin tocar código.

### 09:00 — Últimas comprobaciones

```bash
bash scripts/verificar.sh                    # todo verde
curl -s <api_url>/salud                      # la API responde
# abrir el front en el móvil y en el portátil
```

### 09:30 — Ensayo con interruptions

**Ensaya con interrupciones.** Alguien hace preguntas estúpidas a mitad del
pitch. Si te descuadras, el jurado pierde la confianza.

### 10:30 — Comprobaciones de sala

- ¿Hay wifi? ¿Hay suficiente señal?
- **Probar el front en la red de la sala**, no solo en la del hotel.
- ¿Funciona el audio? ¿El proyector?
- Si el wifi falla, hay una versión local: `python3 -m http.server` en
  `frontend/` (funciona en modo demo).

### 11:00 — Presentaciones

10 minutos por equipo (confirmar con la organización). Los equipos-presentan
en orden, así que **no puedes ver a los demás antes**.

### Después — Declarar winners

---

## 6. Preguntas del jurado — respuestas preparadas

Están en el README principal (§8), pero estas son las que **más probablemente** van a
salir. Llévalas ensayadas, no improvisadas.

### "¿Esto no es un ERP con IA?"

Un ERP **registra el pasado**; nosotros **decidimos el futuro**. Pero lo
importante es otro: el ERP no sabe la fiscalidad andorrana de tu caso.
Nuestro motor tiene la CASS, el IRPF escalonado y el IGI codificados, y por eso
puede decirte el punto exacto en que subir tu facturación deja de compensar.

### "¿Cómo evitas alucinaciones numéricas?"

Separación estricta: **el LLM no hace aritmética**. Toda proyección, umbral de
tramo, IRPF o IGI se calcula en código determinista en Lambda. La IA elige qué
herramienta llamar y redacta la explicación, y cada respuesta cita la regla
aplicada. Es verificable línea por línea, y el motor tiene tests contra los
valores publicados por CASS y el Govern d'Andorra.

### "Enséñame un número que un ERP daría mal"

El mejor: **el IRPF no es 5%**. Todo el mundo publica 0/5/10. El cálculo real
da un tipo efectivo que sube del 0% al 2% de forma progresiva entre 24.000€ y
40.000€, y el tope de la bonificación (800€) cae **exactamente** en 40.000€. A
26.000€ tu tipo efectivo es 0,38%, no 5%.

Segundo: **el crossover de la CASS**. Facturar 45.000€ en vez de 40.000€ suma
**+1.763,88€/año** de cotización, porque la CASS es un coste fijo por tramo.

### "¿Qué pasa con la privacidad?"

Todo vive en la **cuenta AWS aislada del equipo**, cifrado con KMS, IAM de
mínimo privilegio, y Bedrock Guardrails anonimiza la PII y bloquea secrets y
prompt injection. Sin training sobre datos del cliente: la IA procesa, no
almacena. Y el DynamoDB tiene TTL de 30 días: los datos se borran solos.

### "¿Por qué a vosotros?"

Porque un banco con la tesorería real del cliente, el broker, la infraestructura
y a Eric Garcia como Head of AI es el único que puede convertir esto en
producto. El hackathon no es el final: es el principio. Y como dijo nuestro CEO,
primero los mejores en casa.

### "¿Es financieramente viable?"

Coste marginal por cliente: céntimos de Bedrock. Retorno: mayor saldo medio en
cuenta profesional, más depósitos, y menos horas de gestor. En un mercado de
23.939 empresas, un punto de retención en un segmento grande vale más que un
producto nuevo en un segmento pequeño.

### "¿Qué pasa si la normativa cambia?"

Los importes están en tablas, no hardcodeados en la lógica. El corpus
normativo se regenera con `python3 normativa/generar_corpus.py` y el motor
actualiza sus tablas. Y la fuente de verdad es pública: BOPA y CASS.

---

## 7. Problemas frecuentes

### "El navegador no tiene fuente de emoji"

Los emojis se ven como cuadros vacíos. Por eso los iconos del front son **SVG
inline**, no emojis. Si ves cuadros, es que alguien ha metido un emoji.

### "La Lambda no encuentra los módulos"

Faltan los `__init__.py` en `engine/`, `agent/` y `lambda/`. Python los
necesita para que funcionen como paquetes dentro del zip. Están, pero no los
borres.

Y el `handler` de Terraform tiene que ser **`lambda.handler.lambda_handler`**,
no `handler.lambda_handler`: el zip tiene `lambda/handler.py`, así que el
módulo es `lambda.handler`. Con el path equivocado la Lambda se despliega
perfectamente y falla en la **primera invocación** con `ModuleNotFoundError`.

`scripts/test_lambda.sh` comprueba las dos cosas (import real + path de
Terraform), así que no debería llegar a este punto. Si llega: mira el primer
assert de la suite de la Lambda.

### "`terraform validate` falla con `headers`"

`headers` es un **atributo** (`headers = ["Origin"]`), no un bloque. Y el
origen de la API necesita `http_port` y `https_port`.

### "La KB no devuelve nada"

La indexación tarda 5-15 minutos. El corpus está en `normativa/` y lo publica
Terraform al bucket con prefijo `normativa/`.

### "El front sale en modo demo"

Significa que no se inyectó `__API_URL__`. Corre `bash scripts/deploy_front.sh`
después del `terraform apply`.

### "El gráfico sale sin cifras en el eje"

El SVG escala del viewBox (640) al ancho real. La fuente se calcula en función
del ancho, y se redibuja al cambiar el tamaño. Si ves el eje vacío, el ancho
real era 0 al dibujar (SVG oculto): se resuelve mostrando el paso antes de
dibujar.

---

## 8. Plan B — demo sin AWS

Si el `terraform apply` falla, o no dan credenciales, o Bedrock no se habilita:

1. El front funciona en **modo demo** con datos precalculados por el motor real.
2. `python3 -m http.server 8000` en `frontend/` → demo local completa.
3. El motor y sus tests siguen funcionando: **el 90% del valor está en el
   motor y el insight fiscal, no en el cloud.**
4. En el pitch, di la verdad: "lo tenemos construido y validado, y esta es la
   versión local con el mismo motor; el despliegue en AWS es una línea de
   Terraform que no nos ha dado tiempo a ejecutar con la cuenta del equipo".

**Un prototipo local que funciona y explica el insight fiscal gana a un
prototipo en AWS que no llega a tiempo.** No sacrifiques el motor por el cloud.

---

## 9. Checklist del día 7

**Infrastructure**
- [ ] Credenciales AWS activas (`aws sts get-caller-identity`)
- [ ] Acceso al GitLab de MoraBanc
- [ ] `terraform init` sin errores
- [ ] `terraform plan` leído y sin sorpresas
- [ ] `terraform apply` completo
- [ ] `terraform output` con las URLs

**IA**
- [ ] Bedrock responde en vivo (no en mock)
- [ ] Las 11 tools devuelven números
- [ ] Guardrails activo (probar con una PII real)
- [ ] KB indexando el corpus

**Demo**
- [ ] Front publicado y cargando desde CloudFront
- [ ] Front probado en móvil real (no solo en el navegador de escritorio)
- [ ] Demo completa en < 6 minutos
- [ ] 3ª ensayo sin mirar notas
- [ ] Alguien externo lo ha visto y lo ha entendido

**Entrega**
- [ ] Todo subido al GitLab de MoraBanc
- [ ] README con lo que hay y lo que no
- [ ] PDF del pitch como backup
- [ ] Capturas de pantalla como backup
- [ ] Demo local por si falla el wifi

---

## 10. Contactos

| Qué | Quién |
|---|---|
| MoraBanc (hackathon, +376 884 884) | Contacto del evento |
| AWS (habilitar modelos, cuota) | AWS partner del evento — Raimon Pou |
| IA / estrategia en MoraBanc | Eric Garcia, Head of AI & Digital Assets |
| Implementación de la infra | Persona 1 del equipo |
| Ensayo y cronómetro | Persona 2 del equipo |
| Normativa y respuestas al jurado | Persona 3 del equipo |

---

**Documento preparado el 24 de octubre de 2026.** Estado verificado:
434 asserts en verde, Terraform validado, front probado en Chromium real.
