# Contribuir al motor de decisiones MoraBanc

Hackathon MoraBanc IA + Finanzas · 7-8 noviembre 2026.

Este repo es el **código maestro**. Las bases del hackathon obligan a subir el
código al **GitLab de MoraBanc**, asi que este repositorio se mantiene en
GitHub como espejo de trabajo y se sincroniza al GitLab oficial (ver
`scripts/sync_gitlab.sh`).

---

## La regla que no se rompe

> **El LLM no hace aritmética.**

Todo numero que sale del sistema se calcula en codigo determinista
(`engine/`), nunca en el prompt ni en el JavaScript del front. Si añades una
capacidad numerica, va en `engine/` con sus tests. Si no, el jurado puede
preguntar *"¿como evitas alucinaciones numericas?"* y la respuesta tiene que
ser verificable linea por linea.

---

## Estructura

```
engine/         MOTOR DETERMINISTA — el cerebro. Sin IA, sin dependencias.
  fiscal_andorra.py   CASS, IRPF, IGI, crossover, simulador
  tesoreria.py        extracto, clasificacion, proyeccion, fugas
  cierre.py           el bucle de cierre: el motor se reporta sobre su consejo
agent/          CAPA DE IA — Bedrock Converse + tool-use. Elige y redacta.
  bedrock_agent.py    11 herramientas, contrato verificado
lambda/         API AWS Lambda (empaquetada y ejecutada en tests)
frontend/       App estatica mobile-first (HTML/CSS/JS puro, sin build)
normativa/      Corpus legal para el RAG (5 documentos, cifras verificadas)
terraform/      Infra AWS 100% IaC — requisito de descalificacion
tests/          Tests del motor, del agente y del bucle de cierre
scripts/        verificar.sh, deploy_front.sh, test_lambda.sh, test_frontend.js
```

---

## Puesta en marcha

Cero dependencias. No hay `pip install`: el motor usa solo la biblioteca
estandar (`Decimal`, `dataclasses`, `csv`, `re`).

```bash
git clone <este-repo> && cd morabanc-hackathon

# Todo lo verificable, en un comando
bash scripts/verificar.sh

# La demo local (modo demo, sin AWS)
cd frontend && python3 -m http.server 8899
# abrir http://localhost:8899/
```

### Que necesitas para la suite completa

| Herramienta | Para que | Si falta |
|---|---|---|
| Python 3.11+ | motor, tests, generadores | obligatorio |
| Terraform >= 1.5 | `terraform validate` | la suite lo omite con aviso |
| Node 18+ + Playwright | test end-to-end del front en Chromium | la suite lo omite con aviso |
| AWS CLI + credenciales | desplegar | el modo demo funciona igual |

`scripts/verificar.sh` nunca falla por tooling ausente: informa de lo que se
ha omitido. Es deliberado — en un hackathon, una suite que no arranca es peor
que una suite que avisa.

---

## Como se verifica

```bash
bash scripts/verificar.sh              # todo
python3 tests/test_fiscal.py           # motor fiscal
python3 tests/test_tesoreria.py        # tesoreria y fugas
python3 tests/test_cierre.py           # bucle de cierre
python3 tests/test_agente.py           # agente y contrato de herramientas
python3 tests/test_formato.py          # formato de euros y texto del pitch
python3 tests/test_terraform.py        # orden de creacion y IaC de la infra
bash scripts/test_lambda.sh            # Lambda empaquetada y ejecutada
cd terraform && terraform validate     # infra AWS
node scripts/test_frontend.js http://localhost:8899/   # front en Chromium
```

En CI (`.github/workflows/verificar.yml`) corre todo lo anterior en cada push.

---

## Reglas del proyecto

1. **El motor no depende de nada.** Solo biblioteca estandar. Si necesitas una
   libreria, justificalo en el PR: el argumento "nada que instalar en el
   portatil del evaluador" vale puntos.
2. **Toda funcion del motor devuelve el detalle del calculo.** La regla
   aplicada se cita en la respuesta: es lo que el jurado tecnico va a leer.
3. **Los importes van en tablas, no hardcodeados en la logica.** La normativa
   cambia; las tablas se regeneran (`normativa/generar_corpus.py`).
4. **Ningun numero en el JavaScript del front.** El front pide, muestra y
   dibuja. Los datos vienen del motor.
5. **Sin emojis en el front.** Iconos SVG inline: los emojis no renderizan en
   muchos sistemas y se ven como cuadros vacios.
6. **Iconos SVG inline, no fuentes de iconos.** Sin dependencias externas.

---

## Commits

Mensajes en castellano, en imperativo, con el alcance:

```
feat(cierre): anade el bucle de cierre del bucle de vuelta
fix(engine): corrige el redondeo del tramo 62,5% de CASS
test(frontend): cubre el perfil de cierre del bucle
docs(readme): actualiza los numeros tras la revision del corpus
```

Un commit = una idea. Si toca el motor, toca tambien sus tests.

---

## Lo que NO se toca despues del dia 7 por la tarde

El `DEPLOY.md` lo dice: no se toca el motor despues de las 18:00 del dia 7
salvo que algo este roto. En esas horas se arregla el front, el guion y los
backups. Un cambio en el motor a las 19:00 es un riesgo sin cobertura.

---

## Contacto

- MoraBanc (hackathon): +376 884 884
- AWS (habilitar modelos, cuota): Raimon Pou
- IA / estrategia en MoraBanc: Eric Garcia, Head of AI & Digital Assets
