# Desplegar en welcomeandorra.com

El front del motor de decisiones se sirve tambien en un **VPS de Hostinger**
con nginx, bajo el dominio `welcomeandorra.com`.

---

## 1. Estado actual

| Pieza | Estado |
|---|---|
| Front subido a `/var/www/welcomeandorra` | ✅ |
| vhost de nginx con `server_name welcomeandorra.com` | ✅ |
| Content-types correctos (css, js, svg, json, csv) | ✅ |
| Verificado en el VPS real (logo, veredicto, métricas, modo presentación) | ✅ |
| **A record del dominio** | ⏳ **pendiente: lo cambia Pedro** |
| Certificado HTTPS (Let's Encrypt) | ⏳ depende del A record |

---

## 2. El cambio de DNS (lo tienes que hacer tú)

En el panel de Hostinger → **DNS / Zona DNS** de `welcomeandorra.com`:

| Tipo | Nombre | Valor |
|---|---|---|
| **A** | `@` | `179.197.243.234` |
| **A** | `www` | `179.197.243.234` |

> **El valor actual es `148.251.93.9`** (un servidor Hetzner en Alemania que
> no responde). Hay que sustituirlo por `179.197.243.234`.
>
> Los nameservers ya son de Hostinger (`ns1/ns2.dns-parking.com`), así que el
> DNS se cambia desde el mismo panel donde está el dominio.

También conviene **borrar** cualquier registro `A` de `www` que apunte a la IP
antigua, y añadir un `CNAME` `www` → `welcomeandorra.com` si lo prefieres.

### Comprobar que ha funcionado

```bash
python3 -c "import socket; print(socket.gethostbyname('welcomeandorra.com'))"
# debe devolver 179.197.243.234
```

La propagación puede tardar de 5 minutos a unas horas.

---

## 3. Después del DNS: emitir el certificado HTTPS

El script detecta si el DNS ya apunta al servidor y emite el certificado solo.
Si el DNS aún no está cambiado, avisa y deja el sitio en HTTP.

```bash
bash scripts/deploy_welcome.sh
```

El certificado se emite con **Let's Encrypt** vía certbot (ya instalado en el
servidor) y se renueva solo. El puerto 443 ya está abierto en el firewall
(ufw).

---

## 4. Modo real vs modo demo

```bash
# Modo demo (por defecto): los datos los genera el motor Python real.
# Los números son IDENTICOS a los de la API en AWS.
bash scripts/deploy_welcome.sh

# Modo real: el front llama a la API en AWS (Bedrock).
API_URL="https://abc123.execute-api.eu-west-1.amazonaws.com" \
  bash scripts/deploy_welcome.sh
```

El script regenera siempre `frontend/data/demo_data.json` con
`frontend/generar_demo_data.py`, que ejecuta el **motor de Python** — nunca
hay números calculados a mano en el front.

---

## 5. Qué hay en el servidor

```
/var/www/welcomeandorra/
├── index.html                    (12 KB)
├── assets/
│   ├── styles.css                (30 KB)
│   ├── app.js                    (49 KB)
│   └── logo-morabanc.svg         (6 KB, logo real del banco)
└── data/
    ├── demo_data.json            (38 KB, generado por el motor)
    └── demo_*.csv                (4 perfiles de extracto)
```

Nginx (`/etc/nginx/sites-available/welcomeandorra.conf`):

- Redirección a HTTPS cuando hay certificado
- Challenge ACME en `/.well-known/acme-challenge/`
- `try_files` con 404 real para rutas inexistentes
- Cache de 5 minutos en assets (el front se actualiza justo antes del pitch)
- `no-cache` en `index.html`
- gzip para css, js, json y svg

---

## 6. Despliegue rápido (manual, si el script falla)

```bash
RAIZ=/data/projects/morabanc_hackathon
cd $RAIZ
python3 frontend/generar_demo_data.py

ssh hvps "mkdir -p /var/www/welcomeandorra/assets /var/www/welcomeandorra/data"
scp frontend/index.html                          hvps:/var/www/welcomeandorra/
scp frontend/assets/*                           hvps:/var/www/welcomeandorra/assets/
scp frontend/data/demo_data.json frontend/data/demo_*.csv \
                                             hvps:/var/www/welcomeandorra/data/
ssh hvps "chown -R www-data:www-data /var/www/welcomeandorra"
```

---

## 7. Nota sobre el DNS del hackathon (AWS)

Este despliegue es **independiente** del del hackathon:

| | Dónde | Para qué |
|---|---|---|
| **Hackathon** | S3 + CloudFront (Terraform) | Requisito de las bases: infra 100% IaC + el código en el GitLab de MoraBanc. Es lo que se presenta el día 8. |
| **welcomeandorra.com** | VPS Hostinger + nginx | El front en un dominio propio, sin depender de AWS. |

El backend (motor + agente de Bedrock) vive en AWS en los dos casos: el front
es estático y solo llama a la API.
