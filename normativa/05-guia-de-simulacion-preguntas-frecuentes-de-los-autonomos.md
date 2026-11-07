---
titulo: Guía de simulación — Preguntas frecuentes de los autónomos
fuente: Simulador construido sobre las reglas de CASS, IRPF e IGI
---

# Guía de simulación — Preguntas frecuentes de los autónomos

**Fuente:** Simulador construido sobre las reglas de CASS, IRPF e IGI

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
