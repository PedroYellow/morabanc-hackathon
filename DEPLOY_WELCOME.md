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

## 7. welcomeandorra.com ya está en AWS (no en el VPS)

Desde el 7 de noviembre de 2026, **todo vive en AWS**. El requisito del
hackathon es infra 100% en AWS, y el dominio propio quedó detrás de
CloudFront:

| Capa | Recurso AWS |
|---|---|
| DNS del dominio | Zona en Hostinger: `ALIAS @` y `CNAME www` → `d1px306wtnmcnv.cloudfront.net` |
| CDN + TLS | CloudFront `E1B4Z63SX4G4H8`, alias `welcomeandorra.com` y `www` |
| Certificado | ACM `a42fa5e0-359e-4189-853b-f7834ae41840` (us-east-1), validado por DNS |
| Front estático | S3 `morabanc-hackathon-dev-datos-539756034803-5397` (cifrado con KMS, OAC) |
| API | API Gateway `768lyxix1a` → Lambda `morabanc-hackathon-dev-api` |
| Motor | Lambda `morabanc-hackathon-dev-motor` + Bedrock |
| Voz | ElevenLabs (agente `agent_5301m6vbwqpnea1spa0mwkyvs2ap`) |

El VPS de Hostinger (`hvps`, `srv2059981`) **ya no sirve el front**: su
configuración de nginx sigue ahí por si hay que volver atrás, pero el
dominario no apunta a él.

### Por qué el front no lleva la API key

El bundle del navegador se puede leer. La clave va en una **CloudFront
Function** (`mora-inject-api-key`) que la añade en el *edge* a las rutas
`/api/*`, `/preguntar` y `/salud`. El navegador pide `/api/preguntar` sin
cabeceras especiales y CloudFront las pone antes de llegar al API Gateway.

Verificado en producción: `window.__API_KEY__` está vacío en el bundle
servido y la API responde con el cálculo real.

### La Function hay que publicarla DESPUÉS de cada apply

Terraform **no publica** las CloudFront Functions: las deja en stage
`DEVELOPMENT`, donde no se ejecutan. Sin publicar, la API responde 403.

```bash
bash scripts/publish_cf_function.sh
```

El script está conectado a `scripts/deploy_front.sh`, que lo llama tras
publicar. Si algún `terraform apply` deja la función sin publicar, este
script la arregla.

### Los Content-Type importan

`aws s3 sync` **no infiere** el Content-Type: los `.html` y `.js` se
quedan como `application/octet-stream` y el navegador los descarga en vez
de mostrarlos. El mapa `local.content_types` del terraform lo arregla, y
`scripts/sync_front_s3.py` lo hace al publicar a mano.

### Publicar el front

```bash
cd /data/projects/morabanc_hackathon
bash scripts/deploy_front.sh
```

O con terraform, que sube los `aws_s3_object` con su Content-Type:

```bash
terraform -chdir=terraform apply
```

Después, invalidar la caché de CloudFront (si no, el front servido
tarda hasta 5 minutos en actualizarse):

```bash
aws cloudfront create-invalidation \
  --distribution-id E1B4Z63SX4G4H8 --paths "/*"
```
