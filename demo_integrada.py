"""
Demo integrada — el guion del pitch, ejecutable de punta a punta.
================================================================
Encadena: extracto CSV -> motor de tesoreria -> motor fiscal -> agente.

Funciona en modo MOCK (sin cuenta AWS). Los numeros son los mismos que
en produccion: el mock solo sustituye la redaccion del LLM, nunca el
calculo.

Uso:
    python3 demo_integrada.py                    # los 3 perfiles
    python3 demo_integrada.py --perfil comercio  # uno concreto
    python3 demo_integrada.py --preguntas        # modo conversacion
"""

import sys, os, json
from datetime import date
from decimal import Decimal as D

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

from agent.bedrock_agent import AgenteFinanciero, ContextoEmpresa  # noqa: E402

PERFILES = {
    "freelance": {
        "csv": "demo_freelance.csv",
        "titulo": "Freelance de servicios — 30.000 €/año",
        "saldo": D("8500"),
        "renta": D("30000"),
        "margen": D("0.70"),
    },
    "comercio": {
        "csv": "demo_comercio.csv",
        "titulo": "Comercio con tienda local — pyme con empleado",
        "saldo": D("14200"),
        "renta": D("45000"),
        "margen": D("0.35"),
    },
    "contratar": {
        "csv": "demo_freelancer_contratar.csv",
        "titulo": "Freelancer con nomina — la pregunta del pitch",
        "saldo": D("3200"),
        "renta": D("28000"),
        "margen": D("0.70"),
    },
    "cierre": {
        "csv": "demo_freelancer_cierre.csv",
        "titulo": "Freelancer que siguio el consejo — el cierre del bucle",
        "saldo": D("6100"),
        "renta": D("30000"),
        "margen": D("0.70"),
        # Fecha en la que el motor dio el consejo.
        "fecha_consejo": date(2026, 7, 1),
    },
}


def sep(c="="):
    print(c * 76)


def titulo(t):
    print()
    sep()
    print(t)
    sep()


def cargar(clave):
    p = PERFILES[clave]
    ruta = os.path.join(RAIZ, "data", p["csv"])
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    return ContextoEmpresa.desde_csv(
        contenido,
        saldo_actual=p["saldo"],
        renta_neta_anual=p["renta"],
        margen_bruto=p["margen"],
        fecha_consejo=p.get("fecha_consejo"),
    )


def demo_perfil(clave):
    p = PERFILES[clave]
    ctx = cargar(clave)
    agente = AgenteFinanciero(ctx, mock=True)

    titulo(f"{p['titulo']}")

    # --- 1. El detector (el gancho) -----------------------------------
    print(">>> PREGUNTA: ¿Cuánto se me está escapando cada mes?")
    r = agente.preguntar("¿Cuánto se me está escapando cada mes?")
    print(r["respuesta"])
    print()

    # --- 2. La tesoreria ------------------------------------------------
    print(">>> PREGUNTA: ¿Cuánto me queda de caja cada mes?")
    r = agente.preguntar("¿Cuánto me queda de caja cada mes?")
    print(r["respuesta"])
    print()

    # --- 3. El crossover fiscal (el insight) ----------------------------
    print(">>> PREGUNTA: ¿Cuándo salta mi tramo de cotización?")
    r = agente.preguntar("¿Cuándo salta mi tramo de cotización?")
    print(r["respuesta"])
    print()

    # --- 4. La decision (el corazon) ------------------------------------
    print(">>> PREGUNTA: ¿Puedo contratar a alguien a 2.400 brutos al mes?")
    r = agente.preguntar("¿Puedo contratar a alguien a 2400 euros al mes?")
    print(r["respuesta"])
    print()

    # --- 5. La segunda vuelta: recalculo en vivo ------------------------
    print(">>> PREGUNTA: ¿Y si el sueldo es de 2.900 en vez de 2.400?")
    r = agente.preguntar("¿Y si es de 2900 euros?")
    print(r["respuesta"])
    print()

    # --- 6. El cierre del bucle (solo si hay fecha de consejo) -----------
    if p.get("fecha_consejo"):
        print(">>> PREGUNTA: ¿Hiciste caso con mis consejos?")
        r = agente.preguntar("¿Hiciste caso con mis consejos?")
        print(r["respuesta"])
        print()

    # --- 7. La traza (para el jurado tecnico) ---------------------------
    print("--- TRAZA DE LLAMADAS A HERRAMIENTAS ---")
    for h in agente.trace:
        print(f"  {h['tool']}({json.dumps(h['input'], default=str)})")
        res = h["resultado"]
        if isinstance(res, dict):
            for k in list(res.keys())[:5]:
                v = res[k]
                if isinstance(v, (int, float, str)) and len(str(v)) < 60:
                    print(f"      {k}: {v}")
    print()


def modo_preguntas(clave):
    """Modo conversacion: escribe preguntas y el agente responde."""
    ctx = cargar(clave)
    agente = AgenteFinanciero(ctx, mock=True)
    titulo("Modo conversacion — escribe tus preguntas (Ctrl+C para salir)")
    print(f"Contexto: {PERFILES[clave]['titulo']}")
    print("Ejemplos:")
    print("  - ¿Cuánto cotizo a la CASS?")
    print("  - ¿Cuánto de IRPF pago?")
    print("  - ¿Cuántos meses me aguanto en caja?")
    print("  - ¿Puedo contratar a alguien a 2500 euros?")
    print()
    while True:
        try:
            q = input("Tu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in ("salir", "exit", "quit"):
            break
        r = agente.preguntar(q)
        print()
        print(r["respuesta"])
        print()


def main():
    args = sys.argv[1:]

    if "--preguntas" in args:
        clave = "freelance"
        for a in args:
            if a.startswith("--perfil="):
                clave = a.split("=", 1)[1]
        modo_preguntas(clave)
        return

    claves = ["freelance", "contratar"]
    for a in args:
        if a.startswith("--perfil="):
            claves = [a.split("=", 1)[1]]

    for c in claves:
        demo_perfil(c)

    # Comparativa final entre los perfiles: el insight en una tabla
    titulo("COMPARATIVA: no todos los autónomos están en el mismo punto")
    print(f"{'Perfil':<14}{'Renta':>10}{'Tramo CASS':>13}{'Cuota/mes':>12}{'Carga fiscal':>14}")
    print("-" * 76)
    for clave, p in PERFILES.items():
        ctx = cargar(clave)
        from engine.fiscal_andorra import tramo_cass_para, cass_anual, irpf
        t = tramo_cass_para(p["renta"])
        i = irpf(base_general=p["renta"])
        carga = cass_anual(t) + i.cuota_total
        print(f"{clave:<14}{float(p['renta']):>10,.0f}{t.nombre:>13}"
              f"{float(t.cuota_mensual):>12,.2f}{float(carga):>14,.2f}")
    print()
    print("El mismo banco, el mismo producto, tres situaciones distintas.")
    print("Un ERP les da el mismo formulario a los tres. Nosotros no.")


if __name__ == "__main__":
    main()
