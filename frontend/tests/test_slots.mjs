// Bateria de pruebas del extractor de slots (voz -> contexto).
//
// El extractor lee lo que el usuario dice (por voz o por texto) y
// saca los datos que el motor necesita: renta neta, margen, saldo y
// actividad. Estos casos fijan el comportamiento: un numero mal
// atribuido cambia los calculos fiscales, asi que "no cuajar" es
// tan importante como "cuajar".
//
// Ejecutar:  node frontend/tests/test_slots.mjs
//
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const aqui = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(aqui, "..", "assets", "app.js"), "utf8");

// Se extrae el bloque de funciones del extractor del bundle real: los
// tests se ejecutan contra el codigo que se despliega, no contra una
// copia.
const ini = app.indexOf("  function normalizarNumero(bruto)");
const fin = app.indexOf("\n  function pintarChips()", ini);
if (ini === -1 || fin === -1) {
  console.error("No se encontro el extractor en assets/app.js");
  process.exit(1);
}
const bloque = app.slice(ini, fin);

// El bloque usa funciones del IIFE principal (escapar, fmt...). Solo
// hace falta lo que el extractor invoca.
const mod = new Function(
  bloque + "\nreturn { extraerSlots, normalizarNumero, fmt };",
)();
const { extraerSlots } = mod;

const casos = [
  // --- Renta neta ---------------------------------------------
  ["facturo 30.000 euros al año", { renta: 30000 }],
  ["mi renta neta es 45000 euros", { renta: 45000 }],
  ["gano 28.500 al año", { renta: 28500 }],
  ["ingreso 60.000 al año", { renta: 60000 }],
  ["ganancia neta 32000", { renta: 32000 }],
  ["soy autonomo y facturo 25.000", { renta: 25000, actividad: "Autonomo" }],
  // "facturacion" NO es renta neta: el motor calcula sobre la renta.
  ["mi facturacion es 50.000 y mi margen un 40%", { margen: 40 }],
  ["mi empresa factura 120.000 al año", {}],
  // Mensual no es renta neta anual.
  ["facturo 8500 al mes", {}],
  ["cobraria 3500 al mes", {}],

  // --- Margen -------------------------------------------------
  ["tengo un margen del 70%", { margen: 70 }],
  ["mi margen es 65%", { margen: 65 }],

  // --- Saldo -------------------------------------------------
  ["tengo 8.500 euros en cuenta", { saldo: 8500 }],
  ["en el banco tengo 12.300", { saldo: 12300 }],
  ["tengo un saldo de 5.200 euros", { saldo: 5200 }],
  ["mi saldo actual son 12.500 euros", { saldo: 12500 }],
  ["tengo 4.500 en el banco", { saldo: 4500 }],
  ["tengo 3.200 en cuenta", { saldo: 3200 }],
  ["tengo 8500 euros", { saldo: 8500 }],
  ["tengo 15.000 euros ahorrados", { saldo: 15000 }],
  ["mi saldo es 7.500", { saldo: 7500 }],
  ["saldo 8500", { saldo: 8500 }],
  // "3 clientes" no es un saldo de 3 euros.
  ["tengo 3 clientes al mes", {}],
  ["el salon tiene 40 clientes al dia", {}],
  ["tengo 2 horas de trabajo al día", {}],

  // --- Actividad ----------------------------------------------
  ["soy freelance de diseño", { actividad: "Freelance de diseño" }],
  ["tengo una tienda de ropa", { actividad: "Tienda de ropa" }],
  ["soy consultant", { actividad: "Consultant" }],
  ["trabajo como autónomo en diseño gráfico", { actividad: "Autónomo en diseño gráfico" }],
  ["soy una consultora de marketing", { actividad: "Consultora de marketing" }],
  ["trabajo en una tienda de ropa", { actividad: "Tienda de ropa" }],
  // "tengo un margen del 70%" no es una actividad.
  ["tengo un margen del 70%", { margen: 70 }],

  // --- Casos combinados (los que mas importan) ---------------
  [
    "facturo 30000 al año y tengo 8500 en cuenta con un margen del 70%",
    { renta: 30000, margen: 70, saldo: 8500 },
  ],
  [
    "facturo 45.000€ al año, tengo 9.000 en cuenta y un margen del 72%",
    { renta: 45000, saldo: 9000, margen: 72 },
  ],
  ["tengo 20.000 en cuenta y facturo 40.000 al año", { saldo: 20000, renta: 40000 }],
  ["saldo 3.200 euros, renta 40.000 al año", { saldo: 3200, renta: 40000 }],
  ["renta neta 30.000 y saldo en cuenta 8.500", { renta: 30000, saldo: 8500 }],
  ["tengo 25.000 en el banco y soy freelance", { saldo: 25000, actividad: "Freelance" }],

  // --- Ruido -------------------------------------------------
  ["no tengo nada", {}],
  ["quiero contratar a alguien", {}],

  // --- Transcripciones reales de ElevenLabs --------------------
  // El ASR devuelve la frase como la oye, con sus tics: comillas
  // around de las palabras, "72 %" con espacio, "9000" sin
  // separador de millares. Estos casos salieron de una sesion de voz
  // real contra el agente de produccion.
  [
    "Hola, soy freelance de diseño. Facturo 45000 al año. Tengo un margen del 72 % y 9000 euros en cuenta.",
    { renta: 45000, margen: 72, saldo: 9000, actividad: "Freelance de diseño" },
  ],
  ["Tengo un margen del 72 % y 9000 euros en cuenta", { margen: 72, saldo: 9000 }],
  // El "%" del 72 no puede contaminar la cifra siguiente: el 9000 es
  // saldo, no un porcentaje.
  ["Facturo 45000 al año, tengo un margen del 72% y 9000 euros", { renta: 45000, margen: 72, saldo: 9000 }],
  ["Año. Tengo un margen del 72 % y 9.000 euros en cuenta.", { margen: 72, saldo: 9000 }],
  // Una cifra en euros sin "en cuenta" sigue siendo saldo.
  ["tengo 9000 euros", { saldo: 9000 }],

  // --- Lo que dice el usuario gana a lo precargado ---------------
  // El portal de empresas precarga la situacion (30.000). Si el
  // usuario habla y dice otra cifra, su palabra es la que vale: el
  // motor no puede calcular sobre un numero que nadie ha dicho.
  ["facturo 60000 al año", { renta: 60000 }],
  ["tengo 12000 euros en cuenta", { saldo: 12000 }],
  ["mi margen es 55%", { margen: 55 }],
];

let ok = 0;
const fallos = [];
for (const [entrada, esperado] of casos) {
  const r = extraerSlots(entrada);
  const coincide = Object.entries(esperado).every(([k, v]) => String(r[k]) === String(v));
  const extra = Object.keys(r).filter((k) => !(k in esperado));
  if (coincide && extra.length === 0) {
    ok++;
  } else {
    fallos.push(
      `  FAIL ${JSON.stringify(entrada)}\n` +
        `       esperado ${JSON.stringify(esperado)} | obtenido ${JSON.stringify(r)}` +
        (extra.length ? ` | claves extra: ${extra}` : ""),
    );
  }
}
fallos.forEach((f) => console.log(f));
console.log(`\n${ok} OK / ${fallos.length} FAIL  (${casos.length} casos)`);
process.exit(fallos.length ? 1 : 0);
