#!/usr/bin/env python3
"""
Genera el corpus normativo para el RAG (Bedrock Knowledge Base).
============================================================
Convierte la normativa andorrana verificada en documentos de texto que la
Knowledge Base indexa. Los ficheros van a frontend/../normativa/ y Terraform
los publica en S3 (prefijo `normativa/`), que es de donde los ingesta el
data source.

Fuentes de verdad (verificadas 23-oct-2026):
  - BOPA Decret 28/2026 (28-ene-2026): salari global mensual mitjà 2.672,52 €
  - CASS: set bases 25%...137,5%, tipus 22%, quotes mensuels
  - Llei 5/2014 de l'IRPF (consolidada amb Llei 5/2025): arts. 35, 37, 43, 46
  - IGI: 4,5%

Uso:
    python3 normativa/generar_corpus.py
"""

import json
import os
import textwrap

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "normativa")

DOCUMENTOS = []


def doc(titulo, fuente, cuerpo):
    DOCUMENTOS.append({"titulo": titulo, "fuente": fuente, "cuerpo": cuerpo})


# ---------------------------------------------------------------------------
doc(
    "CASS — Cotización por cuenta propia 2026",
    "BOPA Decret 28/2026 (28-ene-2026) · CASS · Llei 11/2023",
    """
BASE DE REFERENCIA

El salario global mensual medio cotizado a la CASS correspondiente a 2025 es de
2.672,52 euros, fijado por el Decreto 28/2026 de 28 de enero de 2026 (BOPA),
un 4,4% superior al del año anterior. Este importe determina la base sobre la
que cotizan los trabajadores por cuenta propia: autónomos, profesionales,
titulares de comercio y administradores de sociedades. Durante 2026 es la base
de cálculo de todas las cotizaciones.

TIPO DE COTIZACIÓN

El tipo general es del 22% sobre la base de cotización: 10% para la rama
general y 12% para la rama de jubilación.

LOS SIETE TRAMOS

Las bases son porcentajes del salario global mensual medio del año anterior.
Según la Ley 11/2023, los tramos son: 25%, 50%, 62,5%, 75%, 100%, 125% y 137,5%.

Tramo 25% — Base 668,13 euros — Cuota mensual 146,99 euros.
  Condición: renta neta inferior a 6.000 euros, o inicio o represa de actividad
  (los 12 primeros meses). También para quien, siendo titular de una actividad,
  es asalariado al menos con el salario mínimo, o es pensionista. Es OPCIONAL:
  hay que solicitarlo.

Tramo 50% — Base 1.525,33 euros — Cuota mensual 335,57 euros.
  Condición: renta neta de 6.000 a 12.000 euros. Para el titular de una
  actividad, renta neta inferior a 12.000 euros salvo que encaje en el 25%.
  OJO: esta base NO es el 50% matemático de 2.672,52 euros (que daría 1.336,26),
  sino el salario mínimo. Desde el 1 de julio de 2026 el salario mínimo es de
  9,05 euros la hora (1.568,67 euros mensuales), de modo que la base de este
  tramo se eleva automáticamente. OPCIONAL: hay que solicitarlo.

Tramo 62,5% — Base 1.670,33 euros — Cuota mensual 367,47 euros.
  Condición: renta neta de 12.000 a 18.000 euros. OPCIONAL.

Tramo 75% — Base 2.004,39 euros — Cuota mensual 440,97 euros.
  Condición: renta neta de 18.000 a 24.000 euros. OPCIONAL.

Tramo 100% — Base 2.672,52 euros — Cuota mensual 587,95 euros.
  Condición: caso general. Reparto: 267,25 euros de rama general (10%) y
  320,70 euros de rama de jubilación (12%). Este es el tramo por defecto.

Tramo 125% — Base 3.340,65 euros — Cuota mensual 734,94 euros.
  Condición: renta neta superior a 40.000 euros. Para el administrador socio
  único o familiar, también una cifra de negocios de la sociedad superior a
  400.000 euros en servicios o a 800.000 euros en otras actividades.
  OBLIGATORIO cuando se cumplen las condiciones.

Tramo 137,5% — Base 3.674,72 euros — Cuota mensual 808,44 euros.
  Condición: renta neta superior a 50.000 euros. Para el administrador socio
  único o familiar, también una cifra de negocios superior a 500.000 euros en
  servicios o a 900.000 euros en otras actividades. OBLIGATORIO.

REGLAS ADICIONALES

Las bases iguales o inferiores al 100% son opcionales: hay que solicitarlas
expressamente a la CASS. Las bases superiores al 100% son obligatorias en
cuanto se cumplen sus condiciones.

Si una persona desarrolla varias actividades, se aplica la base más alta
resultante del conjunto de los ingresos.

Para el administrador socio único, o socio junto con familiares hasta el
segundo grado, las bases reducidas requieren además que la sociedad tenga una
cifra de negocios inferior a 300.000 euros en servicios o a 600.000 euros en
las demás actividades.

La cotización de un trabajador por cuenta propia comienza con el inicio de la
actividad económica. En caso de constitución de una sociedad, la obligación de
cotizar no comienza inmediatamente: empieza 30 días naturales después de la
inscripción en el Registre de Societats.

La cotización total sobre un salario es del 22%: el 6,5% a cargo del asalariado y
el 15,5% a cargo de la empresa.
""",
)

doc(
    "IRPF — Impost sobre la renda de les persones fisiques",
    "Llei 5/2014 de l'IRPF (consolidada amb Llei 5/2025) · Departament de Tributs i de Fronteres",
    """
NORMATIVA

Imposto sobre la renta de las personas físicas (IRPF), aprobado por la Ley 5/2014
de 24 de abril, con las modificaciones de la Ley 5/2025 de 6 de marzo (crecimiento
sostenible y derecho a la vivienda). Grava la renta obtenida por las personas
físicas que tengan la condición de residente fiscal en el territorio andorrano.
El texto consolidado figura en la jurisprudencia.ad, actualizado a 23 de octubre
de 2026.

TIPO DE GRAVAMEN

El tipo de gravamen del impuesto es del 10 por ciento (artículo 43).

REDUCCIÓN POR MÍNIMO PERSONAL EXEMPT (artículo 35)

Los obligados tributarios pueden reducir la base de tributación general en un
importe de 24.000 euros. Este importe se incrementa a 30.000 euros cuando el
obligado tributario se encuentra en situación de incapacidad.

El importe se incrementa a 40.000 euros cuando el cónyuge no separado o la pareja
estable que convive con el obligado tributario no percibe ningún tipo de renta
que se haya de incluir dentro de la base de tributación general. Si el cónyuge o
la pareja obtiene rentas a incluir en la base general, y su importe no permite
aplicar íntegramente la reducción prevista, el obligado tributario puede gaudir
de la cantidad restante, sin que el importe conjunto aplicable por ambos pueda
exceder de 40.000 euros.

REDUCCIÓN POR CARGAS FAMILIARES (artículo 35)

Se puede reducir la base en 1.000 euros por cada descendiente menor de 25 años
a la fecha de meritación del impuesto que conviva con el obligado tributario o
de él dependa y no perciba rendes anuales superiores al salario mínimo
interprofesional; por cada ascendiente mayor de 65 años en las mismas
condiciones; y por cada persona que conviva o de él dependa por razón de tutela
o acogida.

REDUCCIÓN POR MÍNIMO EXEMPT DE LAS RENDES DE AHORRO (artículo 37)

La base de tributación del ahorro se reduce en un importe de 3.000 euros en
concepto de mínimo exempt por obtención de rendes del ahorro.

BONIFICACIÓN POR OBTENCIÓN DE RENDAS DEL TRABAJO, DE ACTIVIDADES ECONÓMICAS O
DEL CAPITAL INMOBILIARIO (artículo 46)

El obligado tributario que haya obtenido rendes del trabajo, de actividades
económicas o del capital inmobiliario, que se integran en la base general del
impuesto, deduce de la cuota de tributación una bonificación del 50 por ciento
de la cantidad que resulte de aplicar el tipo de gravamen del impuesto (10%) sobre
el importe de la base de tributación general del obligado tributario, minorada en
el importe correspondiente a la reducción por mínimo personal a que tiene
derecho. El importe de esta bonificación en ningún caso puede superar el límite
máximo de 800 euros.

CONSECUENCIA PRÁCTICA: EL "5%" PUBLICADO ES UNA SIMPLIFICACIÓN

Si se aplica la bonificación de forma simplificada, tomando el 5% efectivo
sobre el tramo de 24.000 a 40.000 euros, se obtiene un resultado que no coincide
con el cálculo real. El cálculo exacto es el siguiente:

Base general 24.000 euros: cuota 0, bonificación 0, cuota total 0, tipo efectivo 0%.
Base general 26.000 euros: base tributable 2.000, cuota 200, bonificación 100,
  cuota total 100, tipo efectivo 0,38%.
Base general 30.000 euros: base tributable 6.000, cuota 600, bonificación 300,
  cuota total 300, tipo efectivo 1,00%.
Base general 35.000 euros: base tributable 11.000, cuota 1.100, bonificación 550,
  cuota total 550, tipo efectivo 1,57%.
Base general 40.000 euros: base tributable 16.000, cuota 1.600, bonificación 800
  (tope máximo), cuota total 800, tipo efectivo 2,00%.
Base general 45.000 euros: base tributable 21.000, cuota 2.100, bonificación 800,
  cuota total 1.300, tipo efectivo 2,89%.
Base general 50.000 euros: base tributable 26.000, cuota 2.600, bonificación 800,
  cuota total 1.800, tipo efectivo 3,60%.

El tope de 800 euros de la bonificación se alcanza exactamente cuando la base
tributable es de 16.000 euros, es decir, cuando la base general es de 40.000
euros. A partir de ese punto la bonificación queda congelada en 800 euros, la
cuota crece a un 10% nominal y el tipo efectivo real continúa subiendo hacia el
10%. Por encima de 40.000 euros, la fórmula se resume en (renta menos 24.000)
por 10% menos 800.

PAGO FRACCIONADO (Reglamento del IRPF, artículo 5)

Durante el mes de septiembre los obligados tributarios deben efectuar un pago
fraccionado. Su base de cálculo es la cuota de liquidación del ejercicio
anterior. Como opción, el obligado tributario puede determinar el importe del
pago fraccionado aplicando un porcentaje del 5% sobre las rendes netas
procedentes de actividades económicas obtenidas en el periodo impositivo
inmediatamente anterior. Esta opción se ejerce al presentar la declaración
correspondiente y no vincula para futuros periodos.

DEDUCCIONES Y OTRAS BONIFICACIONES

La cuota de tributación puede minorarse por: deducciones para eliminar la doble
imposición interna e internacional; deducción por proyectos que fomenten la
digitalización; deducción por creación de puestos de trabajo; deducciones por
incentivos fiscales al patrocinio y al mecenazgo; deducciones por Reply
participación en proyectos declarados de interés nacional; y reducción por
inversión en vivienda habitual o en vivienda de alquiler a precio asequible.
""",
)

doc(
    "IGI — Impost sobre les activitats economiques",
    "Impost sobre activitats economiques · Departament de Tributs i de Fronteres",
    """
TIPO

El IGI grava el rendimiento de las actividades económicas con un tipo del 4,5%
sobre la base imponible. Es un tipo muy inferior al 21% de IVA que se aplica en
España, y es una de las bases de la ventaja fiscal de operar desde Andorra.

DETERMINACIÓN DE LA RENTA NETA

La determinación de la renta de las actividades económicas en la modalidad de
estimación directa se hace de acuerdo con las normas del impuesto sobre
sociedades, sin perjuicio de las normas especiales establecidas en el
Reglamento del IRPF (artículo 5).

Los gastos deducibles de las rendes de actividades económicas se pueden
cuantificar, a opción del obligado tributario, siguiendo cualquiera de los
criterios siguientes:

a) Conforme a las normas para determinar la renta neta en el régimen de
   determinación directa establecido en el artículo 16.
b) En el 40% del importe de las rendes íntegras, de acuerdo con los requisitos
   y condiciones establecidos en el artículo 17.

Los obligados tributarios pueden aumentar en un 10% el porcentaje anterior,
respecto de los ingresos excluidos de la répercussionión de suministros, por
renta de vivienda habitual y permanente situada en el Principality, siempre que
la renta del alquiler sea inferior a 9 euros el metro cuadrado y el importe
total de la renta no supere los 1.250 euros mensuales. El obligado tributario que
se acoja a este criterio debe comunicarlo al ministerio antes de finalizar el
año anterior al del periodo impositivo en el que se pretenda que tenga efecto,
debiendo 유지 las condiciones durante un plazo mínimo de tres años.

PAGO FRACCIONADO DE SETIEMBRE

El artículo 5 del Reglamento del IRPF prevé que en el mes de septiembre los
obligados tributarios efectúen un pago fraccionado. Se aplica un porcentaje del
5% sobre las rendes netas procedentes de actividades económicas obtenidas en el
periodo impositivo inmediatamente anterior. La elección de este criterio de
cálculo se ejerce en el momento de presentar la declaración y no vincula para
futuros periodos impositivos. La declaración del IRPF relativa al ejercicio 2025
se presenta entre el 1 de abril y el 30 de septiembre de 2026.

ZONA FRANCA Y OTRAS EXENCIONES

Las empresas que operan bajo el régimen de la zona franca de actividades
económicasulae enjoys de exenciones y bonificaciones específicas. Los campos
de actividad económica con bonificación son la investigación y el desarrollo,
la vietnamita de nuevas tecnologías, la producción de energía renovable y la
economía circular. El tratamiento debe verificarse caso por caso con el
Departament de Tributs i de Fronteres.

DEDUCCIONES A LA BASE DE TRIBUTACIÓN

Tratándose de actividades económicas, la base de tributación general se reduce
por nuevas inversiones y por creación de puestos de trabajo.
""",
)

doc(
    "IRNR — Impost sobre la renda dels no residents fiscals",
    "Impost sobre la renda dels no residents fiscals · Departament de Tributs i de Fronteres",
    """
RÉGIME DES FRONTERERS I TEMPORERS

El impuesto sobre la renta de los no residentes fiscales (IRNR) se aplica a los
trabajadores frontereros y temporeros, que no son considerados residentes fiscales
en Andorra. Los rendimientos obtenidos por los frontereros y temporeros quedan
sujetos al IRNR, si bien pueden optar por aplicar el régimen especial del mismo
impuesto.

NOVEDADES DE NOVIEMBRE DE 2025

El Gobierno aprobó una modificación del Reglamento del IRNR que introduce
nuevas simplificaciones en la gestión de los trabajadores frontereros y
temporeros. Esta reforma es relevante para las empresas con personal
temporal, porque reduce la carga administrativa y aclara el tratamiento de
estos trabajadores.

CONTEXTO

Desde el 1 de enero de 2024 está en vigor el Decreto 596/2023 de 29 de
diciembre de 2023, por el que se aprueba el Reglamento del IRPF. El artículo 5
establece que la determinación directa de la renta de las actividades económicas
se hace conforme a las normas del impuesto sobre sociedades.

CONVENIO PARA EVITAR LA DOBLE IMPOSICIÓN

Andorra mantiene convenios para evitar la doble imposición con varios países.
En diciembre de 2025 entró en vigor el CDI con Rumanía. En 2026 se ha
publicado además el CDI con España, con las adaptaciones al nuevo contexto de
fiscalidad internacional. Los CDI pueden modificar el tipo efectivo de un
trabajadorresident en una u otra jurisdicción, por lo que deben revisarse caso
por caso.
""",
)

doc(
    "Guía de simulación — Preguntas frecuentes de los autónomos",
    "Simulador construido sobre las reglas de CASS, IRPF e IGI",
    """
PREGUNTA: ¿Cuánto cotizo a la CASS?

El importe depende de tu renta neta anual. La tabla completa está en el
documento de CASS. En resumen: hasta 6.000 euros de renta neta, tramo 25%; de
6.000 a 12.000, tramo 50%; de 12.000 a 18.000, tramo 62,5%; de 18.000 a 24.000,
tramo 75%; de 24.000 a 40.000, tramo 100% (587,95 euros al mes); de 40.000 a
50.000, tramo 125% (734,94 euros); más de 50.000, tramo 137,5% (808,44 euros).

PREGUNTA: ¿Me compensa facturar más?

No siempre. La CASS es un coste fijo por tramo que no escala con tus ingresos,
así que al cruzar un umbral el coste fiscal puede dar un salto. El punto
crítico está en 40.000 euros de renta neta: ahí la bonificación del IRPF llega
al tope de 800 euros, la CASS pasa del 100% al 125% y el IRPF efectivo acelera.
Calcular el punto óptimo de facturación requiere simular la carga fiscal total
(CASS más IRPF) en función de la renta.

PREGUNTA: ¿Puedo contratar a un empleado?

Sí, y es gasto deducible: no cambia tu renta neta, de modo que la CASS y el IRPF
se mantienen. Lo que cambia es la caja. Para cubrir el coste anual del empleado
más el IGI sobre la facturación adicional, con un margen bruto del 70%,
necesitas facturar aproximadamente 1,49 veces el coste anual en facturación bruta.

PREGUNTA: ¿Qué es el pago fraccionado de septiembre?

Es un pago del 5% de las rendes netas de actividades económicas del periodo
impositivo anterior, que se realiza en septiembre. La base de cálculo
alternativa es la cuota de liquidación del ejercicio anterior.

PREGUNTA: ¿Por qué la gente dice que el IRPF es 0%, 5% y 10%?

Porque es una simplificación. La bonificación del artículo 46 es del 50% sobre
el 10% con un tope de 800 euros, y eso hace que el tipo efectivo real suba de
forma progresiva del 0% al 2% entre 24.000 y 40.000 euros de base. A partir de
40.000 euros, con la bonificación congelada, el tipo nominal del 10% se aplica
sin más reducción.

PREGUNTA: ¿Cuándo se borran mis datos?

La plataforma no almacena tu extracto más de 90 días en el almacenamiento y los
registros de escenarios tienen un tiempo de vida de 30 días. Los datos se
cifran en reposo y se anonimizan los datos personales antes de pasarlos al
modelo de lenguaje.
""",
)


def slug(texto):
    """Nombre de fichero seguro: solo [a-z0-9-], sin acentos ni caracteres raros."""
    import unicodedata
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("—", " ").replace("/", " ")
    t = "".join(c if (c.isalnum() or c in " -") else " " for c in t)
    t = "-".join(t.split())
    return t[:60].strip("-")


def main():
    os.makedirs(DESTINO, exist_ok=True)

    # Un .md por documento, con frontmatter para el data source
    for i, d in enumerate(DOCUMENTOS, 1):
        nombre = f"{i:02d}-{slug(d['titulo'])}.md"
        ruta = os.path.join(DESTINO, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(f"---\n")
            f.write(f"titulo: {d['titulo']}\n")
            f.write(f"fuente: {d['fuente']}\n")
            f.write(f"---\n\n")
            f.write(f"# {d['titulo']}\n\n")
            f.write(f"**Fuente:** {d['fuente']}\n\n")
            f.write(d["cuerpo"].strip() + "\n")
        print(f"  {nombre} ({os.path.getsize(ruta)} bytes)")

    # Un indice para el retrieval
    indice = {
        "documentos": [
            {"titulo": d["titulo"], "fuente": d["fuente"]} for d in DOCUMENTOS
        ],
        "nota": "Corpus generado por normativa/generar_corpus.py. Los importes "
                "están verificados contra BOPA, CASS y Govern d'Andorra (23-oct-2026).",
    }
    with open(os.path.join(DESTINO, "indice.json"), "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=2)

    print(f"\n  → {DESTINO} ({len(DOCUMENTOS)} documentos)")


if __name__ == "__main__":
    main()
