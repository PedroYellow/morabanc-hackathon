#!/usr/bin/env python3
"""Genera la narracion del video.

PROVEEDOR
  ElevenLabs es la opcion de calidad, pero la key del hackathon esta
  AGOTADA (quota_exceeded, 0 creditos de 40.000). Se usa el motor TTS
  de Edge, que es gratuito, sin cuota y tiene voz buena en espanol.

  Para cambiar a ElevenLabs cuando haya saldo: poner USE_ELEVENLABS=1 y
  tener ELEVENLABS_API_KEY con creditos en /data/.env.

Mide la duracion real de cada mp3 con ffprobe: la linea de tiempo se
construye con las duraciones medidas, nunca estimadas.
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "audio")
os.makedirs(OUT, exist_ok=True)

USE_ELEVENLABS = os.environ.get("USE_ELEVENLABS", "0") == "1"

# Edge: "es-ES-XimenaNeural" (femenina, profesional, clara).
# Es la voz por defecto de Windows en espanol.
EDGE_VOICE = "es-ES-XimenaNeural"

# ElevenLabs: Sarah (Mature, Reassuring, Confident). Es el mismo nombre
# que usa el agente del producto, asi que el video suena como la plataforma.
EL_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
EL_MODEL_ID = "eleven_multilingual_v2"

SEGMENTOS = {
    # S1: apertura, el producto se presenta en primera persona
    "s1": "Hola. Soy el asesor financiero de MoraBanc. Pedro me ha construido en dos días. Déjame enseñarte cómo trabajo.",
    # S2: el problema
    "s2": "Todo el mundo te dice que el IRPF andorrà es cero, cinco o diez por ciento. Es una simplificación de marketing. Y es falsa.",
    # S3: el hallazgo
    "s3": "Porque la bonificación real es la mitad del diez por ciento, con un tope de ochocientos euros. Y ese tope se alcanza exactamente en cuarenta mil euros de base.",
    "s3c": "Y en cuanto pasas de cuarenta mil, el tope se congela, el IRPF acelera, y la CASS salta del cien al ciento veinticinco por ciento. Un ERP contable no te enseña este matiz.",
    # S4: como se usa
    "s4": "Así se usa. Tres pasos. Uno: subes el extracto de tu banco. Es un CSV, no un formulario. Dos: yo calculo. IRPF, IGI, CASS, tesorería, las fugas de gasto. Tres: te lo explico con la regla aplicada.",
    # S5: la garantia
    "s5": "Y esto es lo más importante de todo. Yo no hago aritmética.",
    "s5b": "El modelo elige qué herramienta del motor llamar y redacta la respuesta. Cada cifra sale de código determinista. No es que yo sea preciso. Es que no puedo inventarme un número.",
    # S6: el bucle de cierre
    "s6": "Y hay una cosa más que no tiene nadie. Me evalúo a mí mismo.",
    "s6b": "Te doy un consejo en enero, guardo la fecha, y en junio vuelvo a mirar si lo cumpliste. Este freelance siguió dos de cuatro. Y ahorró veintitrés euros y noventa y ocho al mes.",
    # S7: la demo
    "s7": "Mira. Este es el caso de verdad. Treinta mil euros de ingresos.",
    "s7b": "Detecto que su caja se agota en el mes nueve, y le digo exactamente por qué. La bonificación se congela en cuarenta mil, la CASS salta al ciento veinticinco, y con eso el flujo se va a menos cuatro mil doscientos sesenta y siete al mes.",
    # S8: la guia
    "s8": "Y si no sabes qué preguntarme, es normal. Pregúntame en lenguaje natural. Yo traduzco a la herramienta correcta.",
    "s8b": "Por ejemplo: cuánto pago de IRPF, qué fugas de gasto tengo, cuándo se me acaba la caja, o qué pasaría si subo la renta. Y siempre te devuelvo tres cosas: la cifra, la regla que la produce, y qué deberías hacer.",
    # S9: cierre
    "s9": "Soy el asesor financiero de MoraBanc. La inteligencia artificial es el interfaz. La norma es el producto.",
    "s9b": "Porque un asesor fiscal no debería estar explicándote porcentajes. Debería explicarte decisiones. Pruébalo en welcomeandorra punto com.",
}


def duracion(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def con_edge(texto, destino):
    """Sintetiza con edge-tts (pip install edge-tts)."""
    import asyncio
    import edge_tts

    async def _run():
        com = edge_tts.Communicate(texto, EDGE_VOICE, rate="+12%")
        await com.save(destino)

    asyncio.run(_run())


def con_elevenlabs(texto, destino):
    import urllib.request

    key = None
    for line in open("/data/.env", encoding="utf-8"):
        line = line.strip()
        if line.startswith("ELEVENLABS_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("no hay ELEVENLABS_API_KEY en /data/.env")

    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE_ID}"
           "?output_format=mp3_44100_128")
    cuerpo = json.dumps({
        "text": texto,
        "model_id": EL_MODEL_ID,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=cuerpo, method="POST", headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        audio = r.read()
    with open(destino, "wb") as f:
        f.write(audio)


def main():
    cronologia = {}
    total = 0.0
    for sid, texto in SEGMENTOS.items():
        destino = os.path.join(OUT, f"{sid}.mp3")
        if not os.path.exists(destino):
            if USE_ELEVENLABS:
                con_elevenlabs(texto, destino)
            else:
                con_edge(texto, destino)
            print(f"  {sid}: generado", flush=True)
        else:
            print(f"  {sid}: ya existia", flush=True)
        d = duracion(destino)
        cronologia[sid] = {
            "inicio": round(total, 3),
            "duracion": round(d, 3),
            "fin": round(total + d + 0.7, 3),
        }
        total += d

    with open(os.path.join(OUT, "timing.json"), "w", encoding="utf-8") as f:
        json.dump({"segmentos": cronologia, "total": round(total, 3)},
                  f, indent=2, ensure_ascii=False)
    print(f"\n  narracion: {total:.1f} s")
    for sid, t in cronologia.items():
        print(f"    {sid}: {t['inicio']:6.2f} -> {t['fin']:6.2f}  ({t['duracion']:.1f}s)")


if __name__ == "__main__":
    main()
