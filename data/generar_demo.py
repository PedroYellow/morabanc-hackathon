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
    "demo_freelancer_contratar.csv": gen_freelancer_contratar,
    "demo_freelancer_cierre.csv": gen_freelancer_cierre,
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
