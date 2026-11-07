#!/usr/bin/env python3
"""Genera las slides de marca del video y de la deck.

Identidad MoraBanc (paleta real extraida de morabanc.ad):
  navy  #0a3550   el color institucional
  gold  #f1c657   el acento (kickers, cifras, filenames)
  fondo #f4f7fa   el gris azulado claro
  card  #ffffff
  texto #1c2b36
  gris  #5a6b78
  verde #04aa6d
  rojo  #f0421c

Tipografia (jerarquia editorial, no un solo sans):
  Source Serif 4  -> titulares
  Inter           -> cuerpo
  JetBrains Mono  -> kickers, cifras, etiquetas tecnicas

Todas las slides son 1920x1080.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "slides")
FONTES = os.path.join(BASE, "fonts")
os.makedirs(OUT, exist_ok=True)

W, H = 1920, 1080

NAVY = (10, 53, 80)
NAVY_CLARO = (17, 66, 116)
GOLD = (241, 198, 87)
GOLD_SOFT = (247, 221, 154)
FONDO = (244, 247, 250)
CARD = (255, 255, 255)
TEXTO = (28, 43, 54)
GRIS = (90, 107, 120)
GRIS_CLARO = (137, 137, 137)
VERDE = (4, 170, 109)
ROJO = (240, 66, 28)
LINEA = (223, 229, 236)


def f(nombre, tam):
    return ImageFont.truetype(os.path.join(FONTES, nombre), tam)


def serif(tam):
    return f("SourceSerif4.ttf", tam)


def sans(tam):
    return f("Inter.ttf", tam)


def mono(tam):
    return f("JetBrainsMono.ttf", tam)


def medir(d, texto, fuente):
    b = d.textbbox((0, 0), texto, font=fuente)
    return b[2] - b[0], b[3] - b[1]


def sombra(base, caja, radio=18, blur=26, alfa=38):
    """Sombra suave bajo una tarjeta. Sin esto la deck parece un wireframe."""
    capa = Image.new("RGBA", base.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    x0, y0, x1, y1 = caja
    dc.rounded_rectangle((x0, y0 + 6, x1, y1 + 10), radius=radio,
                         fill=(10, 30, 50, alfa))
    capa = capa.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(capa)


def logo(d, x, y, alto=54):
    """El logo real de MoraBanc, dibujado (no el SVG: el SVG es para web).

    Reproduce el mark: un cuadrado navy con la "M" en gold y el nombre
    al lado en mayusculas con tracking.
    """
    lado = alto
    d.rounded_rectangle((x, y, x + lado, y + lado), radius=int(lado * 0.16),
                        fill=NAVY)
    # La "M" en gold, centrada
    ft = sans(int(lado * 0.58))
    d.text((x + lado / 2, y + lado / 2 - lado * 0.03), "M",
           font=ft, fill=GOLD, anchor="mm")
    # El nombre
    ftn = sans(int(alto * 0.34))
    d.text((x + lado + alto * 0.30, y + lado / 2), "MORA BANC",
           font=ftn, fill=NAVY, anchor="lm")
    return x + lado + alto * 0.30 + medir(d, "MORA BANC", ftn)[0]


def fondo_base():
    img = Image.new("RGBA", (W, H), FONDO + (255,))
    d = ImageDraw.Draw(img)
    # Un halo navy muy suave arriba a la derecha: da profundidad sin ruido
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dh = ImageDraw.Draw(halo)
    dh.ellipse((1250, -420, 2250, 580), fill=NAVY + (16,))
    halo = halo.filter(ImageFilter.GaussianBlur(120))
    img.alpha_composite(halo)
    return img


def pie(d, texto_izq, numero=None):
    """Pie de slide: linea fina + credito + numero.

    El pie va a H-210, no a H-96: los subtitulos quemados ocupan dos lineas
    de 50 px (~130 px) desde el borde inferior. Con el pie abajo, el
    subtitulo lo tapaba. Hay tres bandas separadas y sin solape:
    la tabla, el pie, y la caja del subtitulo.
    """
    d.line((110, H - 214, W - 110, H - 214), fill=LINEA, width=2)
    ft = mono(24)
    d.text((110, H - 190), texto_izq, font=ft, fill=GRIS_CLARO)
    if numero:
        d.text((W - 110, H - 190), numero, font=ft, fill=GRIS_CLARO, anchor="ra")


def kicker(d, x, y, texto, color=GOLD, tam=26):
    ft = mono(tam)
    d.text((x, y), texto.upper(), font=ft, fill=color)
    return y + tam + 22


def titular(d, x, y, texto, tam=88, color=NAVY, ancho_max=1600):
    """Titular en serif. Parte en lineas si no cabe."""
    ft = serif(tam)
    palabras = texto.split()
    lineas, actual = [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if medir(d, prueba, ft)[0] <= ancho_max:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    for linea in lineas:
        d.text((x, y), linea, font=ft, fill=color)
        y += int(tam * 1.12)
    return y


def tarjeta(img, d, caja, radio=20):
    """Tarjeta con sombra suave. img es la imagen, d su ImageDraw."""
    sombra(img, caja, radio=radio)
    d.rounded_rectangle(caja, radius=radio, fill=CARD, outline=LINEA, width=2)


def pie_de_tarjeta(d, x, y, texto, tam=25, color=GRIS):
    d.text((x, y), texto, font=sans(tam), fill=color)


# ---------------------------------------------------------------------------
# Las slides
# ---------------------------------------------------------------------------

def s_portada():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    # Banda navy a la izquierda
    d.rectangle((0, 0, 18, H), fill=NAVY)
    logo(d, 120, 96, 62)
    y = kicker(d, 120, 268, "Hackathon IA + Finanzas", GOLD, 28)
    y = titular(d, 120, y, "El asesor que explica", 104)
    d.text((120, y), "decisiones, no porcentajes", font=serif(104), fill=NAVY)
    y += 150
    d.text((120, y), "MoraBanc Asesor Financiero IA",
           font=sans(46), fill=GRIS)
    d.text((120, y + 62), "Motor determinista de fiscalidad y tesorería andorrana",
           font=sans(30), fill=GRIS_CLARO)
    # Tarjeta con la URL
    tarjeta(img, d, (120, H - 320, 900, H - 180))
    d.text((168, H - 288), "welcomeandorra.com", font=mono(34), fill=NAVY)
    d.text((168, H - 238), "en vivo, en español, con el motor real detrás",
           font=sans(24), fill=GRIS)
    return img


def s_problema():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "El problema")
    y = titular(d, 110, y, "El 0% / 5% / 10%", 92)
    d.text((110, y), "es una simplificación de marketing", font=serif(92), fill=NAVY)
    y += 140
    # Lo que todos dicen
    tarjeta(img, d, (110, y, 880, y + 250))
    d.text((150, y + 34), "Lo que se publica", font=mono(24), fill=GRIS_CLARO)
    d.text((150, y + 76), "0%  5%  10%", font=serif(76), fill=GRIS)
    d.text((150, y + 176), "Tres números y ninguna explicación",
           font=sans(26), fill=GRIS)
    # Lo que es
    tarjeta(img, d, (940, y, 1810, y + 250))
    d.rectangle((940, y, 946, y + 250), fill=GOLD)
    d.text((990, y + 34), "Lo que dice la norma", font=mono(24), fill=GOLD)
    d.text((990, y + 76), "50% del 10%, tope 800 €", font=serif(56), fill=NAVY)
    d.text((990, y + 176), "Y el tope depende de tu base",
           font=sans(26), fill=GRIS)
    y += 320
    d.text((110, y), "Sin el matiz, un 26.000 € de base paga un tipo efectivo del 0,38%, "
                    "no del 5%.", font=sans(31), fill=TEXTO)
    pie(d, "MoraBanc · Asesor Financiero IA", "02")
    return img


def s_hallazgo():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 200, "El hallazgo")
    y = titular(d, 110, y, "El tope de 800 €", 76)
    d.text((110, y), "se alcanza en 40.000 € exactos", font=serif(76), fill=NAVY)
    y += 112
    # Tabla de la bonificacion
    filas = [
        ("24.000 €", "0 €", "0 €", "0,00%", False),
        ("30.000 €", "300 €", "300 €", "1,00%", False),
        ("35.000 €", "550 €", "550 €", "1,57%", False),
        ("40.000 €", "800 €", "800 € (tope)", "2,00%", True),
        ("45.000 €", "1.300 €", "800 €", "2,89%", False),
    ]
    x0 = 110
    anchos = [420, 330, 400, 330]
    cab_y = y
    cx = x0
    for i, tit in enumerate(["Base general", "Cuota IRPF", "Bonificación", "Tipo efectivo"]):
        d.text((cx + 24, cab_y), tit.upper(), font=mono(22), fill=GOLD)
        cx += anchos[i]
    y += 46
    d.line((x0, y, x0 + sum(anchos), y), fill=NAVY, width=3)
    y += 18
    for base, cuota, boni, tipo, destaque in filas:
        if destaque:
            tarjeta(img, d, (x0 - 16, y - 8, x0 + sum(anchos) - 24, y + 62), radio=12)
        cx = x0
        for i, val in enumerate([base, cuota, boni, tipo]):
            ft = sans(31) if not destaque else sans(33)
            col = NAVY if destaque else TEXTO
            if i == 2 and destaque:
                col = VERDE
            d.text((cx + 24, y), val, font=ft, fill=col)
            cx += anchos[i]
        y += 62
    y += 14
    # La consecuencia. Se queda por encima del pie (H-214).
    tarjeta(img, d, (110, y, 1810, y + 152), radio=16)
    d.rectangle((110, y, 116, y + 152), fill=ROJO)
    d.text((150, y + 28), "A partir de 40.000 €: la bonificación se congela, "
                          "el IRPF acelera y la CASS salta del 100% al 125%.",
           font=sans(30), fill=TEXTO)
    d.text((150, y + 84), "Un ERP contable no te enseña este matiz. "
                          "Por eso hay un motor, no un chatbot.",
           font=sans(25), fill=GRIS)
    pie(d, "MoraBanc · Asesor Financiero IA", "03")
    return img


def s_solucion():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "La solución")
    y = titular(d, 110, y, "Un motor que calcula,", 88)
    d.text((110, y), "una IA que explica", font=serif(88), fill=NAVY)
    y += 140
    pasos = [
        ("1", "Subes tu extracto", "CSV del banco. Sin formularios, sin集成."),
        ("2", "El motor calcula", "IRPF, IGI, CASS, tesorería y fugas de gasto."),
        ("3", "La IA explica", "Con la regla aplicada y la cifra de tu caso."),
    ]
    x = 110
    for num, tit, sub in pasos:
        tarjeta(img, d, (x, y, x + 540, y + 290))
        d.text((x + 40, y + 34), num, font=serif(72), fill=GOLD)
        d.text((x + 40, y + 128), tit, font=sans(36), fill=NAVY)
        d.text((x + 40, y + 182), sub, font=sans(25), fill=GRIS)
        x += 570
    y += 350
    d.text((110, y), "El resultado: una respuesta que puedes auditar, "
                    "no una opinion de una caja negra.",
           font=sans(32), fill=TEXTO)
    pie(d, "MoraBanc · Asesor Financiero IA", "04")
    return img


def s_tesis():
    img = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(img)
    # Halo gold muy tenue
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dh = ImageDraw.Draw(halo)
    dh.ellipse((1150, -380, 2150, 620), fill=GOLD + (20,))
    halo = halo.filter(ImageFilter.GaussianBlur(130))
    img.alpha_composite(halo)
    d = ImageDraw.Draw(img)

    d.text((120, 130), "LA TESIS", font=mono(28), fill=GOLD)
    d.text((120, 300), "La IA es el interfaz;", font=serif(112), fill=(255, 255, 255))
    d.text((120, 430), "la norma es el producto.", font=serif(112), fill=GOLD)

    d.line((120, 620, 1800, 620), fill=(255, 255, 255, 40), width=2)

    izq = [
        "El LLM no hace aritmética.",
        "Elige la herramienta del motor y redacta.",
        "Cada cifra sale de código determinista.",
        "Cada respuesta cita el artículo aplicado.",
    ]
    y = 690
    for linea in izq:
        d.ellipse((126, y + 12, 142, y + 28), fill=GOLD)
        d.text((172, y), linea, font=sans(36), fill=(232, 238, 244))
        y += 68

    d.text((120, H - 168), "Y eso es la respuesta a «¿cómo evitas alucinaciones numéricas?»",
           font=sans(28), fill=(150, 172, 190))
    d.text((W - 120, H - 168), "05", font=mono(24), fill=(110, 138, 160), anchor="ra")
    return img


def s_motor():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "El motor")
    y = titular(d, 110, y, "11 herramientas,", 88)
    d.text((110, y), "cero caja negra", font=serif(88), fill=NAVY)
    y += 130
    grupos = [
        ("Fiscal", ["tramo IRPF", "bonificación 46", "IGI", "CASS", "crossover"]),
        ("Tesorería", ["parseo extractos", "fugas de gasto", "proyección de caja", "quiebre"]),
        ("Cierre", ["informe de cierre", "consejos", "cumplimiento"]),
    ]
    x = 110
    for tit, items in grupos:
        w = 540
        tarjeta(img, d, (x, y, x + w, y + 380))
        d.text((x + 34, y + 32), tit.upper(), font=mono(24), fill=GOLD)
        yy = y + 88
        for it in items:
            d.ellipse((x + 36, yy + 11, x + 48, yy + 23), fill=NAVY)
            d.text((x + 66, yy), it, font=sans(29), fill=TEXTO)
            yy += 50
        x += 570
    y += 425
    d.text((110, y), "Cada herramienta devuelve la cifra y la regla que la produce. "
                    "El modelo redacta encima, nunca debajo.",
           font=sans(31), fill=TEXTO)
    pie(d, "MoraBanc · Asesor Financiero IA", "06")
    return img


def s_garantia():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "El riesgo que todos(Equal)")
    y = titular(d, 110, y, "El modelo no toca", 86)
    d.text((110, y), "ni un solo numero", font=serif(86), fill=NAVY)
    y += 140
    # Diagrama: pregunta -> router -> motor -> respuesta
    cajas = [
        ("Pregunta", "«¿Cuánto me queda\nde IRPF?»", 330),
        ("Router", "Elige la herramienta\npor intencion", 330),
        ("Motor Python", "Calcula en codigo\ndeterminista", 380),
        ("Respuesta", "Cifra + articulo\n+ tramo aplicado", 380),
    ]
    x = 110
    yc = y
    for i, (tit, sub, w) in enumerate(cajas):
        es_motor = i == 2
        tarjeta(img, d, (x, yc, x + w, yc + 210))
        d.rectangle((x, yc, x + w, yc + 6), fill=GOLD if es_motor else NAVY)
        d.text((x + 28, yc + 32), tit, font=sans(33), fill=NAVY)
        for j, linea in enumerate(sub.split("\n")):
            d.text((x + 28, yc + 92 + j * 42), linea, font=sans(25), fill=GRIS)
        if i < len(cajas) - 1:
            ax = x + w + 18
            d.polygon([(ax, yc + 96), (ax + 34, yc + 105), (ax, yc + 114)], fill=GOLD)
        x += w + 52
    y = yc + 268
    # Lo que no puede pasar
    tarjeta(img, d, (110, y, 1810, y + 170), radio=16)
    d.rectangle((110, y, 116, y + 170), fill=VERDE)
    d.text((150, y + 30), "Una IA que multiplica 30.000 por 5% te da 1.500 € y sonria.",
           font=sans(30), fill=TEXTO)
    d.text((150, y + 84), "La nuestra te dice 300 € y te cita el articulo 46 del IRPF.",
           font=sans(30), fill=VERDE)
    pie(d, "MoraBanc · Asesor Financiero IA", "07")
    return img


def s_cierre():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "El bucle de cierre")
    y = titular(d, 110, y, "El motor se evalúa", 88)
    d.text((110, y), "a sí mismo", font=serif(88), fill=NAVY)
    y += 140
    # Traza de meses
    d.line((150, y + 90, 1770, y + 90), fill=LINEA, width=6)
    meses = [("ENE", VERDE), ("FEB", VERDE), ("MAR", VERDE), ("ABR", GRIS_CLARO),
             ("MAY", VERDE), ("JUN", ROJO), ("JUL", GRIS_CLARO), ("AGO", GRIS_CLARO)]
    x = 175
    for m, col in meses:
        d.ellipse((x - 18, y + 72, x + 18, y + 108), fill=col)
        d.text((x, y + 128), m, font=mono(22), fill=GRIS, anchor="ma")
        x += 222
    y += 210
    # Resultado
    tarjetas = [
        ("2 de 4", "consejos seguidos", NAVY),
        ("23,98 €/mes", "ahorro acumulado", VERDE),
        ("7 meses", "de histórico real", NAVY),
    ]
    x = 110
    for cifra, sub, col in tarjetas:
        tarjeta(img, d, (x, y, x + 540, y + 190))
        d.text((x + 34, y + 34), cifra, font=serif(66), fill=col)
        d.text((x + 34, y + 120), sub, font=sans(25), fill=GRIS)
        x += 570
    y += 250
    d.text((110, y), "El motor vuelve a mirar lo que dijo en enero y comprueba "
                    "si lo cumpliste en junio.",
           font=sans(31), fill=TEXTO)
    pie(d, "MoraBanc · Asesor Financiero IA", "08")
    return img


def s_demo():
    img = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(img)
    d.text((120, 120), "EN VIVO", font=mono(28), fill=GOLD)
    d.text((120, 180), "El caso del freelance", font=serif(80), fill=(255, 255, 255))
    d.text((120, 278), "30.000 € de ingresos · extractos del banco",
           font=sans(32), fill=(168, 190, 208))
    # Las 4 metricas, como en el modo presentacion
    m = [
        ("CASS", "587,95 €/mes", VERDE),
        ("Flujo mensual", "-4.267,05 €", ROJO),
        ("Quiebre de caja", "Mes 9", GOLD),
        ("Base IRPF", "30.000 €", (255, 255, 255)),
    ]
    x = 120
    y = 430
    for tit, val, col in m:
        tarjeta(img, d, (x, y, x + 400, y + 200))
        d.text((x + 30, y + 30), tit.upper(), font=mono(21), fill=GRIS_CLARO)
        d.text((x + 30, y + 82), val, font=serif(52), fill=col)
        x += 420
    # El veredicto
    y += 260
    d.text((120, y), "«Tu caja se agota en el mes 9»", font=serif(62), fill=GOLD)
    d.text((120, y + 88), "y te dice exactamente por qué: la bonificación se congela "
                          "en 40.000 € y la CASS salta al 125%.",
           font=sans(30), fill=(176, 196, 212))
    d.text((120, H - 150), "welcomeandorra.com", font=mono(30), fill=(120, 148, 172))
    d.text((W - 120, H - 150), "09", font=mono(24), fill=(110, 138, 160), anchor="ra")
    return img


def s_arquitectura():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "Arquitectura")
    y = titular(d, 110, y, "Todo en AWS,", 88)
    d.text((110, y), "100% en IaC", font=serif(88), fill=NAVY)
    y += 130
    capas = [
        ("Frontend", "S3 + CloudFront · ES/CA/EN · sin build", NAVY),
        ("API", "API Gateway v2 · Lambda · API key + authorizer", NAVY),
        ("Agente", "Bedrock Converse con tool-use (11 herramientas)", GOLD),
        ("Conocimiento", "OpenSearch Serverless + corpus normativo", NAVY),
        ("Infraestructura", "Terraform · IAM con roles por función · KMS", NAVY),
    ]
    yc = y
    for tit, sub, col in capas:
        tarjeta(img, d, (110, yc, 1810, yc + 104))
        d.rectangle((110, yc, 118, yc + 104), fill=col)
        d.text((150, yc + 22), tit, font=sans(33), fill=NAVY)
        d.text((150, yc + 66), sub, font=sans(25), fill=GRIS)
        yc += 118
    pie(d, "MoraBanc · Asesor Financiero IA", "10")
    return img


def s_verificacion():
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 226, "Verificacion")
    y = titular(d, 110, y, "No lo digamos:VGamoslo", 86)
    y += 130
    cifras = [
        ("526", "asserts automaticos", "motor, tesoreria, cierre, agente, IaC"),
        ("15", "bugs de IaC corregidos", "encontrados ejecutando el apply real"),
        ("0", "alucinaciones posibles", "todo numero sale de codigo"),
    ]
    x = 110
    for cifra, tit, sub in cifras:
        tarjeta(img, d, (x, y, x + 540, y + 330))
        d.text((x + 40, y + 30), cifra, font=serif(104), fill=NAVY)
        d.text((x + 40, y + 168), tit, font=sans(30), fill=TEXTO)
        d.text((x + 40, y + 216), sub, font=sans(23), fill=GRIS)
        x += 570
    y += 388
    d.text((110, y), "La suite corre en cada push. Si el motor deja de cuadrar, "
                    "el CI se pone rojo.",
           font=sans(31), fill=TEXTO)
    pie(d, "MoraBanc · Asesor Financiero IA", "11")
    return img


def s_final():
    img = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(img)
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dh = ImageDraw.Draw(halo)
    dh.ellipse((1150, -380, 2150, 620), fill=GOLD + (22,))
    halo = halo.filter(ImageFilter.GaussianBlur(130))
    img.alpha_composite(halo)
    d = ImageDraw.Draw(img)

    logo(d, 120, 110, 60)
    d.text((120, 300), "La IA es el interfaz.", font=serif(100), fill=(255, 255, 255))
    d.text((120, 420), "La norma es el producto.", font=serif(100), fill=GOLD)

    d.line((120, 590, 1800, 590), fill=(255, 255, 255, 40), width=2)

    d.text((120, 650), "Porque un asesor fiscal no debería estar explicándote porcentajes:",
           font=sans(34), fill=(176, 196, 212))
    d.text((120, 706), "debería explicarte decisiones.", font=sans(34), fill=(255, 255, 255))

    tarjeta(img, d, (120, H - 300, 940, H - 150))
    d.text((168, H - 272), "welcomeandorra.com", font=mono(36), fill=NAVY)
    d.text((168, H - 220), "probalo ahora, en espanol", font=sans(24), fill=GRIS)

    d.text((W - 120, H - 240), "12", font=mono(24), fill=(110, 138, 160), anchor="ra")
    d.text((W - 120, H - 190), "MoraBanc · Asesor Financiero IA",
           font=sans(24), fill=(110, 138, 160), anchor="ra")
    return img



def s_guia():
    """La guia del agente: como preguntarle y que te devuelve."""
    img = fondo_base()
    d = ImageDraw.Draw(img)
    logo(d, 110, 86, 52)
    y = kicker(d, 110, 200, "Como se usa")
    y = titular(d, 110, y, "Pregúntame en", 76)
    d.text((110, y), "lenguaje natural", font=serif(76), fill=NAVY)
    y += 108

    # Columna izquierda: preguntas de ejemplo
    d.text((110, y), "EJEMPLOS", font=mono(22), fill=GOLD)
    preguntas = [
        ("\u00bfCuánto pago de IRPF con 30.000 \u20ac?", "Tramo + bonificación"),
        ("\u00bfQué fugas de gasto tengo?", "Análisis del extracto"),
        ("\u00bfCuándo se me acaba la caja?", "Proyección y quiebre"),
        ("\u00bfY si subo a 40.000 \u20ac?", "Recalculo completo"),
        ("\u00bfCumplí mis consejos?", "Informe de cierre"),
    ]
    yy = y + 40
    for pre, acc in preguntas:
        d.text((110, yy), pre, font=sans(27), fill=TEXTO)
        d.text((110, yy + 36), acc, font=sans(22), fill=GRIS_CLARO)
        yy += 74

    # Columna derecha: que te devuelve
    x2 = 960
    tarjeta(img, d, (x2, y, 1810, y + 400))
    d.text((x2 + 36, y + 30), "SIEMPRE TE DEVOLVERGO", font=mono(22), fill=GOLD)
    yy = y + 84
    for i, (tit, sub) in enumerate([
        ("La cifra", "el número, y solo el número"),
        ("La regla que la produce", "artículo, tramo, fórmula"),
        ("Qué deberías hacer", "la acción concreta"),
    ]):
        d.ellipse((x2 + 36, yy + 8, x2 + 56, yy + 28), fill=GOLD)
        d.text((x2 + 78, yy), tit, font=sans(32), fill=NAVY)
        d.text((x2 + 78, yy + 42), sub, font=sans(23), fill=GRIS)
        yy += 100
    d.line((x2 + 36, yy + 2, 1774, yy + 2), fill=LINEA, width=2)
    d.text((x2 + 36, yy + 22), "Nunca solo el número.", font=sans(29), fill=VERDE)
    pie(d, "MoraBanc · Asesor Financiero IA", "13")
    return img


SLIDES = {
    "d01": s_portada, "d02": s_problema, "d03": s_hallazgo, "d04": s_solucion,
    "d05": s_tesis, "d06": s_motor, "d07": s_garantia, "d08": s_cierre,
    "d09": s_demo, "d10": s_arquitectura, "d11": s_verificacion, "d12": s_final,
    "d13": s_guia,
}


def main():
    for nombre, fn in SLIDES.items():
        img = fn().convert("RGB")
        destino = os.path.join(OUT, f"{nombre}.png")
        img.save(destino, "PNG")
        print(f"  {nombre}.png  {img.size}")
    print(f"\n  {len(SLIDES)} slides en {OUT}")


if __name__ == "__main__":
    main()
