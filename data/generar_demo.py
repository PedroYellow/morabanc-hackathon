"""
Generador de extractos de demo — autonomos y pymes andorranos realistas.
Genera movimientos sinteticos pero verosimiles (fiscalidad y precios reales
de Andorra) para tener datos de prueba sin datos personales de terceros.

Uso:
    python3 data/generar_demo.py            # genera los 3 CSV
    python3 data/generar_demo.py --mostrar  # muestra el extracto generado
"""

import os
import random
from datetime import date, timedelta

random.seed(20261107)   # semilla fija: la demo siempre da los mismos numeros

AQUI = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# 1. FREELANCE DE SERVICIOS — 30.000 €/año (el caso del pitch)
# --------------------------------------------------------------------------

def gen_freelance() -> list[dict]:
    m = []
    inicio = date(2025, 10, 1)
    fin = date(2026, 9, 30)

    # Facturacion irregular: 3-4 facturas grandes al mes, importes variables
    for mes in range(12):
        anyo = 2025 if mes < 3 else 2026
        mes_num = (10 + mes - 1) % 12 + 1
        f = date(anyo, mes_num, 5)
        if f < inicio or f > fin:
            continue
        # Tres facturas: una grande, una mediana, una pequena
        for concepto, base in [
            ("FACTURA SERVICIOS PROFESIONALES", 2600),
            ("Factura proyecto clientes", 1150),
            ("Factura mantenimiento mensual", 320),
        ]:
            jitter = random.randint(-140, 180)
            importe = max(80, base + jitter)
            m.append({"fecha": f, "concepto": concepto, "importe": importe})

        # Gastos del mes
        for concepto, importe in [
            ("CASS cotitzacio treball per compte propi", 587.95),
            ("Impost IGI trimestre", 675.00),
            ("Lloguer coworking", 450.00),
            ("Electricitat ENEL", random.randint(95, 165)),
            ("Internet i telefonia fibra", 78.90),
            ("Assegurances professional", 42.50),
            ("Targeta credit comissions", 3.20),
            ("Material d'oficina", random.randint(40, 130)),
        ]:
            df = date(anyo, mes_num, random.randint(2, 27))
            if inicio <= df <= fin:
                m.append({"fecha": df, "concepto": concepto, "importe": -abs(importe)})

        # Suscripciones (una se detecta como fuga)
        for concepto, importe in [
            ("Suscripcion ADOBE CREATIVE CLOUD", 59.99),
            ("NETFLIX.COM", 12.99),
            ("SPOTIFY PREMIUM", 10.99),
            ("DROPBOX PROFESIONAL", 19.99),
        ]:
            df = date(anyo, mes_num, random.randint(3, 12))
            if inicio <= df <= fin:
                m.append({"fecha": df, "concepto": concepto, "importe": -abs(importe)})

        # Gastos de desplazamiento
        for _ in range(random.randint(2, 5)):
            df = date(anyo, mes_num, random.randint(1, 28))
            if inicio <= df <= fin:
                m.append({
                    "fecha": df,
                    "concepto": random.choice(["Gasoil Repsol", "Parking centre", "Uber BCN", "Peaje AP-7"]),
                    "importe": -abs(round(random.uniform(28, 95), 2)),
                })

    return m


# --------------------------------------------------------------------------
# 2. COMERCIO CON TIENDA — pyme con mas volumen
# --------------------------------------------------------------------------

def gen_comercio() -> list[dict]:
    m = []
    inicio = date(2025, 10, 1)
    fin = date(2026, 9, 30)

    for mes in range(12):
        anyo = 2025 if mes < 3 else 2026
        mes_num = (10 + mes - 1) % 12 + 1

        # Ventas diarias (TPV)
        dias = 30 if mes_num in (1, 3, 5, 7, 8, 10, 12) else 28
        for d in range(1, dias + 1):
            df = date(anyo, mes_num, d)
            if not (inicio <= df <= fin):
                continue
            for _ in range(random.randint(3, 8)):
                m.append({
                    "fecha": df,
                    "concepto": "TPV VENTA TARJETA",
                    "importe": round(random.uniform(18, 145), 2),
                })

        for concepto, importe in [
            ("CASS treball per compte propi", 734.94),
            ("Impost IGI trimestre", 1890.00),
            ("Lloguer local comercial", 1850.00),
            ("Sous empleat", 2100.00),
            ("CASS empleat", 455.00),
            ("Compra mercaderia", random.randint(3200, 5400)),
            ("Electricitat Endesa comerç", random.randint(180, 320)),
            ("Targeta Visa empresa", 24.90),
        ]:
            df = date(anyo, mes_num, random.randint(2, 27))
            if inicio <= df <= fin:
                m.append({"fecha": df, "concepto": concepto, "importe": -abs(importe)})

    return m



# --------------------------------------------------------------------------
# 3-bis. CERAMICA CANILLO — pyme a 2.000 EUR del umbral de tramo
# --------------------------------------------------------------------------
#
# El escenario del cuarto usuario (12TJ31). No puede compartir extracto
# con el comercio de tienda: si lo hiciera, el jurado veria el mismo
# extracto bajo dos razones sociales distintas.
#
# La historia: un taller de ceramica con UN empleado y un local mas
# pequeño que la tienda. Su caja aguanta, pero esta a 2.000 EUR del
# salto de tramo (40.000 € de renta neta), que es justo la pregunta:
# "compensa facturar mas o me quedo en el tramo de al lado?"

def gen_ceramica() -> list[dict]:
    m = []
    inicio = date(2025, 10, 1)
    fin = date(2026, 9, 30)

    for mes in range(12):
        anyo = 2025 if mes < 3 else 2026
        mes_num = (10 + mes - 1) % 12 + 1

        # Las ventas del taller: menos volumen que la tienda, tickets
        # mas altos (una pieza de ceramica decorativa cuesta mas que
        # un producto de tienda).
        dias = 30 if mes_num in (1, 3, 5, 7, 8, 10, 12) else 28
        for d in range(1, dias + 1):
            df = date(anyo, mes_num, d)
            if not (inicio <= df <= fin):
                continue
            for _ in range(random.randint(3, 5)):
                m.append({
                    "fecha": df,
                    "concepto": "TPV VENTA TARJETA",
                    "importe": round(random.uniform(36, 118), 2),
                })

        for concepto, importe in [
            # CASS del dueño (tramo 100 %, 587,95 €/mes) y del empleado
            # (tramo 75 %). La diferencia con el comercio es que aqui
            # hay UN empleado, no dos.
            ("CASS treball per compte propi", 587.95),
            ("CASS empleat", 455.00),
            ("Sous empleat", 1950.00),
            # Alquiler del taller: mas barato que una tienda en el centro.
            ("Lloguer taller", 1150.00),
            # IGI: un cuarto de la facturacion, que es lo que se paga.
            ("Impost IGI trimestre", 1580.00),
            ("Compra materia prima", random.randint(1150, 1950)),
            ("Electricitat Endesa taller", random.randint(140, 260)),
            ("Targeta Visa empresa", 24.90),
        ]:
            df = date(anyo, mes_num, random.randint(2, 27))
            if inicio <= df <= fin:
                m.append({"fecha": df, "concepto": concepto, "importe": -abs(importe)})

    return m


# --------------------------------------------------------------------------
# 3. FREELANCER QUE ESTA POR CONTRATAR — el caso de la pregunta del pitch
# --------------------------------------------------------------------------

def gen_freelancer_contratar() -> list[dict]:
    m = gen_freelance()
    # Salario fijo: hace que su caja sea justa y la pregunta tenga tension
    for mes in range(12):
        anyo = 2025 if mes < 3 else 2026
        mes_num = (10 + mes - 1) % 12 + 1
        df = date(anyo, mes_num, 28)
        if date(2025, 10, 1) <= df <= date(2026, 9, 30):
            m.append({"fecha": df, "concepto": "NOMINA ADMINISTRATIVA SL", "importe": -2100.00})
    return m


# --------------------------------------------------------------------------
# 4. FREELANCER QUE SIGUIO EL CONSEJO — el cierre del bucle de vuelta
# --------------------------------------------------------------------------

#: Fecha en la que el motor dio el consejo: dia 1 de julio de 2026.
FECHA_CONSEJO = date(2026, 7, 1)


def gen_freelancer_cierre() -> list[dict]:
    """
    El escenario del cierre del bucle, y el que se ensena en el pitch.

    Mayo y junio de 2026: el autonomo tiene 4 suscripciones que no usa.
    El 1 de julio el motor le dice que las cancele.
    De julio a septiembre: 2 las cancela (NETFLIX y SPOTIFY) y 2 las mantiene
    (ADOBE, que usa para facturar, y DROPBOX, que le parece barato).

    Al corte de septiembre, el motor se reporta sobre su propio consejo:
    "Has seguido 2 de 4 recomendaciones. Llevas ahorrados 23,98 €/mes".
    """
    m = gen_freelance()

    # Las 2 suscripciones que el usuario CANCELA tras el consejo: quitamos
    # sus cargos de julio a septiembre.
    canceladas = ("NETFLIX", "SPOTIFY")
    m = [
        x for x in m
        if not (
            x["fecha"] >= FECHA_CONSEJO
            and any(c in x["concepto"].upper() for c in canceladas)
        )
    ]

    # Una adicion al extracto: la primera nomina pagada con la caja recuperada.
    # Refuerza la historia del pitch (contratar con el ahorro del motor).
    m.append({
        "fecha": date(2026, 8, 28),
        "concepto": "NOMINA ADMINISTRATIVA SL",
        "importe": -1200.00,
    })

    return m



# --------------------------------------------------------------------------
# 5. USUARIO NORMAL — asalariado sin actividad economica
# --------------------------------------------------------------------------
# Un empleado de empresa no lleva contabilidad: no tiene factura de
# ingresos, sino una nomina. El caso sirve para:
#   - Mostrar que el asesor tambien habla con quien no es autonomo.
#   - Probar el caso "renta de wages": el IRPF ya viene retenido y lo
#     que se calcula es la IRPF complementaria y el IRNR si trabaja
#     para una empresa de fuera.
#   - Ver el caso "sin actividad economica": sin IGI, sin CASS propia.
#
# Perfil: empleado de una empresa andorriana, 2.400 brutos/mes.
# Lo que ve el motor es una nomina limpia, un alquiler, luz, comida y
# suscripciones: el caso tipico de "tengo una cuenta y no entiendo por
# que no me llega a fin de mes".

def gen_empleado() -> list[dict]:
    m = []
    inicio = date(2025, 10, 1)
    fin = date(2026, 9, 30)

    # Nomina mensual: 2.400 brutos, IRPF retenido
    for mes in range(12):
        anyo = 2025 if mes < 3 else 2026
        mes_num = (10 + mes - 1) % 12 + 1
        f = date(anyo, mes_num, 28)
        if f < inicio or f > fin:
            continue
        # El neto que entra en la cuenta (bruto menos IRPF y CASS del
        # empleado). Con 2.400 brutos el neto ronda 1.940.
        m.append({"fecha": f, "concepto": "NOMINA TRABAJADORS ALTORDA SA",
                  "importe": 1940.12})

        # Gastos del mes
        for concepto, importe in [
            ("Lloguer pis", 950.00),
            ("Electricitat ENDESA", random.randint(58, 105)),
            ("Aigua SMA", random.randint(18, 34)),
            ("Internet i mobil ORANGE", 59.90),
            ("Gasolina REPSOL", random.randint(45, 95)),
            ("Compres i supermercat", random.randint(320, 480)),
            ("Restaurant i superficies", random.randint(120, 260)),
            ("Farmacia", random.randint(15, 70)),
            ("Gimnas", 45.00),
            ("Streaming NETFLIX", 12.99),
            ("Spotify Premium", 10.99),
            ("Targeta credit comissions", 2.50),
        ]:
            df = date(anyo, mes_num, random.randint(1, 27))
            if inicio <= df <= fin:
                m.append({"fecha": df, "concepto": concepto, "importe": -abs(importe)})

    # Un ingreso extra: devolucion de la garantia del alquiler
    m.append({"fecha": date(2026, 7, 15),
              "concepto": "DEVOLUCIO GARANTIA LLOGUER",
              "importe": 950.00})

    return m


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------

def escribir_csv(nombre: str, movimientos: list[dict]) -> str:
    ruta = os.path.join(AQUI, nombre)
    movimientos = sorted(movimientos, key=lambda x: (x["fecha"], x["concepto"]))
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write("Fecha;Concepto;Importe\n")
        for m in movimientos:
            imp = f"{m['importe']:.2f}".replace(".", ",")
            f.write(f"{m['fecha'].strftime('%d/%m/%Y')};{m['concepto']};{imp}\n")
    return ruta


PERFILES = {
    "demo_freelance.csv": gen_freelance,
    "demo_comercio.csv": gen_comercio,
    "demo_ceramica.csv": gen_ceramica,
    "demo_freelancer_contratar.csv": gen_freelancer_contratar,
    "demo_freelancer_cierre.csv": gen_freelancer_cierre,
    "demo_empleado.csv": gen_empleado,
}


def main():
    mostrar = "--mostrar" in __import__("sys").argv
    for nombre, gen in PERFILES.items():
        movs = gen()
        ruta = escribir_csv(nombre, movs)
        ingresos = sum(m["importe"] for m in movs if m["importe"] > 0)
        gastos = sum(-m["importe"] for m in movs if m["importe"] < 0)
        print(f"{nombre}: {len(movs)} movimientos | ingresos {ingresos:,.0f} € | "
              f"gastos {gastos:,.0f} € | flujo {ingresos - gastos:,.0f} €")
        if mostrar:
            with open(ruta, encoding="utf-8") as f:
                for i, linea in enumerate(f):
                    if i > 14:
                        print("    ...")
                        break
                    print("   ", linea.rstrip())


if __name__ == "__main__":
    main()
