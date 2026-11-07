#!/usr/bin/env python3
"""Monta el video: slides de marca + capturas reales de la web.

La linea de tiempo sale de las duraciones MEDIDAS de la narracion
(pitch/audio/timing.json), nunca de estimaciones.

Salida:
  pitch/rec/     frames de video 1920x1080 (slides + capturas de la web)
  pitch/timeline.json
  pitch/video/morabanc_pitch.mp4
"""
import json
import os
import subprocess

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(BASE, "audio")
SLIDES = os.path.join(BASE, "slides")
REC = os.path.join(BASE, "rec")
RECZ = os.path.join(BASE, "recz")
VIDEO = os.path.join(BASE, "video")
FPS = 25

for d in (RECZ, VIDEO):
    os.makedirs(d, exist_ok=True)

# ---------------------------------------------------------------------------
# La secuencia: que se ve mientras se oye cada segmento.
# "slide" = slide de marca, "web" = captura de la web real.
# ---------------------------------------------------------------------------
SECUENCIA = [
    # (segmento, [ (tipo, archivo, peso_extra) ... ])
    ("s1",   [("slide", "d01", 0.0)]),
    ("s2",   [("slide", "d02", 0.0)]),
    ("s3",   [("slide", "d03", 0.0)]),
    ("s3c",  [("slide", "d03", 0.0)]),
    ("s4",   [("slide", "d04", 0.0)]),
    ("s5",   [("slide", "d07", 0.0)]),
    ("s5b",  [("slide", "d07", 0.0)]),
    ("s6",   [("slide", "d08", 0.0)]),
    ("s6b",  [("slide", "d08", 0.0)]),
    # La demo: la web real es la protagonista
    ("s7",   [("web", "f002", 1.0)]),
    ("s7b",  [("web", "f004", 2.6), ("web", "f005", 2.2),
              ("web", "f006", 3.2), ("web", "f007", 1.0)]),
    # La guia
    ("s8",   [("slide", "d13", 0.0)]),
    ("s8b",  [("slide", "d13", 0.0)]),
    ("s9",   [("slide", "d12", 0.0)]),
    ("s9b",  [("slide", "d12", 0.0)]),
]


def leer_audio(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def audio_total():
    """Mezcla los 9 segmentos con 0,7 s de respiro entre ellos."""
    entradas = []
    for i, (sid, _) in enumerate( enumerate_seg()):
        pass
    return entradas


def enumerate_seg():
    for sid, _ in SECUENCIA:
        yield sid


def construir_audio():
    """Concatena los segmentos con pausas y devuelve la duracion total."""
    segs = [sid for sid, _ in SECUENCIA]
    pausa = 0.7
    partes = []
    for i, sid in enumerate(segs):
        archivo = f"{AUDIO}/{sid}.mp3"
        partes.append(archivo)
    # Con el demuxer de concat + silencios entre medias.
    lista = os.path.join(VIDEO, "audio_concat.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for i, sid in enumerate(segs):
            f.write(f"file '{os.path.join(AUDIO, sid)}.mp3'\n")
            if i < len(segs) - 1:
                # Un silencio de la pausa entre segmentos
                f.write(f"file '{os.path.join(VIDEO, 'pausa.mp3')}'\n")
    # El silencio se genera una vez
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", str(pausa), "-c:a", "libmp3lame", "-b:a", "128k",
         os.path.join(VIDEO, "pausa.mp3")],
        capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista,
         "-c:a", "libmp3lame", "-b:a", "192k",
         os.path.join(VIDEO, "narracion.mp3")],
        capture_output=True)
    return leer_audio(os.path.join(VIDEO, "narracion.mp3"))


def frames_de_web(archivos, duracion_total):
    """Genera los frames de video a partir de capturas y duraciones.

    Cada captura se queda quieta un rato (un video de una app real se ve
    mejor con pausas que si se moviesen todos los frames a 25 fps).
    """
    salida = []
    n = 0
    for nombre, dur in archivos:
        origen = os.path.join(REC, f"{nombre}.png")
        img = Image.open(origen).convert("RGB")
        # Se renombra a f<NNN>.png en recz para que el concat sea facil
        n += 1
        destino = os.path.join(RECZ, f"w{n:03d}.png")
        img.save(destino, "PNG")
        salida.append((destino, dur))
    return salida


def main():
    with open(os.path.join(AUDIO, "timing.json"), encoding="utf-8") as f:
        timing = json.load(f)

    print("==> Construyendo la narracion")
    total_audio = construir_audio()
    print(f"    duracion: {total_audio:.2f} s")

    # Reparte el tiempo de cada segmento entre sus imagenes.
    print("==> Repartiendo el tiempo entre las imagenes")
    plan = []
    for sid, items in SECUENCIA:
        dur_seg = timing["segmentos"][sid]["duracion"]
        # El padding de 0,7 s se lo damos al ultimo item de cada segmento
        # menos en el ultimo segmento (ahi va al final).
        peso = [it[2] if len(it) > 2 else 0 for it in items]
        suma_extra = sum(peso)
        if len(items) == 1:
            asignadas = [dur_seg]
        else:
            # Reparto proporcional a los pesos. El peso minimo de 0,35
            # hace que ninguna imagen se quede sin tiempo. La suma se
            # ajusta al final para cuadrar con la duracion medida.
            asig = [dur_seg * (p + 0.35) / (sum(peso) + 0.35 * len(items))
                    for p in peso]
            asig[-1] += dur_seg - sum(asig)
            # Ningun frame puede durar menos de medio segundo: una duracion
            # negativa o casi cero rompe el demuxer de concat.
            if asig[-1] < 0.5:
                deficit = 0.5 - asig[-1]
                asig[-1] = 0.5
                for i in range(len(asig) - 1):
                    if asig[i] - deficit >= 0.5:
                        asig[i] -= deficit
                        break
            asignadas = asig
        for it, dur in zip(items, asignadas):
            plan.append((sid, it, dur))

    # Los frames de la web (varios por segmento) y las slides.
    print("==> Preparando los frames")
    frames = []
    idx = 0
    for sid, item, dur in plan:
        tipo, nombre = item[0], item[1]
        if tipo == "slide":
            origen = os.path.join(SLIDES, f"{nombre}.png")
        else:
            origen = os.path.join(REC, f"{nombre}.png")
        idx += 1
        destino = os.path.join(RECZ, f"v{idx:03d}.png")
        if not os.path.exists(destino) or True:
            Image.open(origen).convert("RGB").save(destino, "PNG")
        frames.append((destino, dur))
        print(f"    {sid} {tipo:5} {nombre}  {dur:5.2f}s")

    # El archivo de concat del demuxer
    lista = os.path.join(VIDEO, "concat.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for ruta, dur in frames:
            f.write(f"file '{ruta}'\nduration {dur:.3f}\n")
        # El ultimo se repite: el demuxer lo necesita para el frame final
        f.write(f"file '{frames[-1][0]}'\n")

    # Los subtitulos, con los tiempos reales de cada segmento
    print("==> Generando los subtitulos")
    with open(os.path.join(VIDEO, "subs.srt"), "w", encoding="utf-8") as f:
        n = 0
        for sid, texto in TEXTO_SUBTITULOS.items():
            t = timing["segmentos"][sid]
            n += 1
            f.write(f"{n}\n")
            f.write(f"{_ts(t['inicio'])} --> {_ts(t['fin'] - 0.15)}\n")
            f.write(texto + "\n\n")

    print("==> Montando el video")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista,
         "-vf", f"fps={FPS},format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         os.path.join(VIDEO, "slides_video.mp4")],
        capture_output=True)

    # La musica de fondo
    print("==> Musica de fondo")
    dur = max(total_audio + 1, 1)
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"sine=frequency=110:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=165:duration={dur}",
         "-filter_complex",
         "[0:a]volume=0.5[a0];[1:a]volume=0.3[a1];[a0][a1]amix=inputs=2,"
         f"lowpass=f=380,tremolo=f=0.4:d=0.15,aecho=0.8:0.9:900:0.25,"
         f"volume=0.11,afade=t=in:st=0:d=3,afade=t=out:st={max(dur-4,0)}:d=4",
         "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k",
         os.path.join(VIDEO, "bgm.mp3")],
        capture_output=True)

    print("==> Mezclando audio")
    subprocess.run(
        ["ffmpeg", "-y",
         "-i", os.path.join(VIDEO, "narracion.mp3"),
         "-i", os.path.join(VIDEO, "bgm.mp3"),
         "-filter_complex",
         "[0:a]volume=1.6,aresample=44100[n];[1:a]volume=0.9[m];"
         "[n][m]amix=inputs=2:duration=longest:normalize=0",
         "-c:a", "aac", "-b:a", "192k",
         os.path.join(VIDEO, "audio.m4a")],
        capture_output=True)

    print("==> Quemando los subtitulos")
    # Tamano de proyector: 50 px, negrita, margenes amplios para que la
    # linea larga envuelva en dos lineas y no en tres.
    estilo = ("FontName=DejaVu Sans,FontSize=50,Bold=1,"
              "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
              "BackColour=&H99000000,BorderStyle=4,Outline=1,Shadow=0,"
              "Alignment=2,MarginV=30,MarginL=80,MarginR=80,WrapStyle=0,"
              "PlayResX=1920,PlayResY=1080")
    subprocess.run(
        ["ffmpeg", "-y",
         "-i", os.path.join(VIDEO, "slides_video.mp4"),
         "-i", os.path.join(VIDEO, "audio.m4a"),
         "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-crf", "21",
         "-c:a", "aac", "-b:a", "192k", "-shortest",
         os.path.join(VIDEO, "con_subs.mp4")],
        capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", os.path.join(VIDEO, "con_subs.mp4"),
         "-vf", f"subtitles={os.path.join(VIDEO, 'subs.srt')}:force_style='{estilo}'",
         "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-crf", "21",
         "-c:a", "copy",
         os.path.join(VIDEO, "morabanc_pitch.mp4")],
        capture_output=True)

    dur_final = leer_audio(os.path.join(VIDEO, "morabanc_pitch.mp4"))
    print(f"\n  Video: {os.path.join(VIDEO, 'morabanc_pitch.mp4')}")
    print(f"  Duracion: {dur_final:.1f} s")
    with open(os.path.join(BASE, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump({"total_audio": total_audio, "duracion_video": dur_final,
                   "frames": [{"archivo": a, "duracion": d} for a, d in frames]},
                  f, indent=2, ensure_ascii=False)


def _ts(segundos):
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = segundos % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


# Cada cue cabe en DOS lineas como maximo. Con 50 px, tres lineas son
# ~190 px de alto y taparian el pie de la slide.
TEXTO_SUBTITULOS = {
    "s1": "Hola. Soy el asesor financiero de MoraBanc.\nPedro me ha construido en dos días.",
    "s2": "Todo el mundo te dice que el IRPF es 0%, 5% o 10%.\nEs una simplificación de marketing. Y es falsa.",
    "s3": "La bonificación real es la mitad del 10%, con un tope de 800 €.\nEse tope se alcanza exactamente en 40.000 € de base.",
    "s3c": "Pasas de 40.000 € y el tope se congela, el IRPF acelera\ny la CASS salta del 100% al 125%.",
    "s4": "Subes el extracto del banco. Yo calculo. Te lo explico\ncon la regla aplicada: el artículo, el tramo, el cálculo.",
    "s5": "Y esto es lo más importante de todo.\nYo no hago aritmética.",
    "s5b": "El modelo elige la herramienta y redacta.\nCada cifra sale de código. No puedo inventarme un número.",
    "s6": "Y hay una cosa más que no tiene nadie.\nMe evalúo a mí mismo.",
    "s6b": "Te doy un consejo en enero y en junio miro si lo cumpliste.\nEste freelance siguió 2 de 4: ahorró 23,98 €/mes.",
    "s7": "Mira. Este es el caso de verdad.\n30.000 € de ingresos.",
    "s7b": "Detecto que su caja se agota en el mes 9 y le digo por qué.\nEl flujo se va a -4.267,05 € al mes.",
    "s8": "Y si no sabes qué preguntarme, es normal.\nPregúntame en lenguaje natural. Yo traduzco.",
    "s8b": "Siempre te devuelvo tres cosas: la cifra,\nla regla que la produce, y qué deberías hacer.",
    "s9": "Soy el asesor financiero de MoraBanc.\nLa IA es el interfaz. La norma es el producto.",
    "s9b": "Un asesor fiscal no debería explicarte porcentajes.\nDebería explicarte decisiones. Pruébalo en welcomeandorra.com.",
}
if __name__ == "__main__":
    main()
