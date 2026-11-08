# El motor, en local

Por que existe
-------------
La Lambda en AWS es el destino de produccion del motor de decisiones:
es el codigo con la normativa andorrana, ejecutandose en la
infraestructura del hackathon (S3 + CloudFront + API Gateway + Lambda).

Pero las credenciales de AWS que da el workshop CADUCAN (en este
momento, el 8 de noviembre de 2026, ya ha pasado dos veces). Sin
credenciales no se puede redesplegar la Lambda, asi que el codigo
nuevo (las decisiones de compra, los idiomas) no llega a la Lambda.

Este servidor es el RESPALDO: el MISMO motor (los mismos ficheros de
`engine/` y `agent/`, el mismo Python, los mismos numeros), corriendo
en el VPS en vez de en la Lambda.

No es una maqueta ni una reimplementacion. Es el motor de verdad en
otro sitio.

Como esta montado
-----------------
- `scripts/motor_local.py`: el servidor HTTP. Mismo contrato que la
  Lambda: `POST /preguntar` con `{pregunta, empresa_id, saldo_actual,
  renta_neta_anual, margen_bruto, actividad}` y respuesta
  `{respuesta, herramientas}`.
- En el VPS: servicio systemd `morabanc-motor` en el puerto 8811,
  escuchando solo en 127.0.0.1.
- En el nginx del VPS: `location = /api/preguntar` enruta al motor
  local; el resto de `/api/` sigue yendo a API Gateway en AWS.

El modo es DETERMINISTA (sin Bedrock): el motor enruta la pregunta con
las mismas reglas del router y ejecuta la herramienta; el texto se
arma con el resultado. Los numeros salen del motor, nunca del LLM.
Cuando la Lambda se redespliegue, esta ruta se puede quitar y todo
vuelve a ir a AWS.

Que hay que hacer cuando haya credenciales
------------------------------------------
1. Desplegar la Lambda con el codigo nuevo:
   `cd terraform && terraform apply`
2. Comprobar que `/api/preguntar` responde con la herramienta
   `evaluar_compra`.
3. Quitar la `location = /api/preguntar` del nginx del VPS:
   `sudo nano /etc/nginx/sites-available/welcomeandorra.conf`
   (borrar el bloque) y `sudo systemctl reload nginx`.
4. Parar el servicio local (opcional):
   `sudo systemctl disable --now morabanc-motor`

Y ya esta: el sitio vuelve a ir por la infraestructura de AWS.
