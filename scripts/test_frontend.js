/**
 * Test end-to-end del frontend con Playwright.
 *
 * Verifica el flujo real en un navegador:
 *   carga -> seleccion de perfil -> analisis -> veredicto -> grafico ->
 *   hallazgos -> chat -> modal -> cambio de idioma -> reinicio
 *
 * Uso:
 *   node test_frontend.js [url]
 *   LD_LIBRARY_PATH=... node test_frontend.js
 */

const path = require("path");
const { chromium } = require("playwright");

const URL = process.argv[2] || "http://localhost:8899/";

let fallos = [];
let n = 0;

function check(nombre, ok, extra) {
  n++;
  const marca = ok ? "PASS" : "FAIL";
  console.log(`  ${marca}  ${nombre}${extra ? " -> " + extra : ""}`);
  if (!ok) fallos.push(nombre);
}

(async () => {
  const browser = await chromium.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },   // iPhone: mobile-first
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();

  const erroresJS = [];
  page.on("pageerror", (e) => erroresJS.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") erroresJS.push("console: " + m.text());
  });

  console.log("\n=== CARGA ===");
  await page.goto(URL, { waitUntil: "networkidle" });
  check("titulo correcto", (await page.title()).includes("MoraBanc"));
  check("paso 1 visible", await page.isVisible("#stepContexto"));
  check("paso 2 oculto", !(await page.isVisible("#stepResultado")));
  check("5 opciones de inicio", (await page.locator("#opcionesInicio .opcion").count()) === 5);
  check("existe el perfil de cierre del bucle",
    (await page.locator('.opcion[data-perfil="cierre"]').count()) === 1);
  check("sin scroll horizontal",
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));

  console.log("\n=== SELECCION DE PERFIL ===");
  await page.click('.opcion[data-perfil="contratar"]');
  await page.waitForTimeout(300);
  check("opcion marcada", await page.locator('.opcion[data-perfil="contratar"]').evaluate(
    (el) => el.classList.contains("selected")));
  const renta = await page.inputValue("#rentaNeta");
  check("renta rellenada desde el perfil", renta === "28000", renta);
  const margen = await page.inputValue("#margenBruto");
  check("margen en %", margen === "70", margen);
  check("zona de upload oculta", !(await page.isVisible("#uploadZone")));

  console.log("\n=== ANALISIS ===");
  await page.click("#btnAnalizar");
  await page.waitForSelector("#stepResultado:not([hidden])", { timeout: 15000 });
  await page.waitForTimeout(600);

  check("paso 2 visible", await page.isVisible("#stepResultado"));
  check("veredicto con texto", (await page.textContent("#verdictTitle")).trim().length > 8,
    (await page.textContent("#verdictTitle")).trim());
  check("metricas pintadas", (await page.locator("#verdictMetrics .metric-value").count()) >= 2);
  check("hallazgos encontrados", (await page.locator("#hallazgos .hallazgo").count()) >= 1,
    String(await page.locator("#hallazgos .hallazgo").count()));
  check("grafico visible", await page.isVisible("#cardProyeccion"));
  check("svg con paths", (await page.locator("#graficoCaja path").count()) >= 2);
  check("nota del grafico", (await page.textContent("#notaProyeccion")).trim().length > 20);
  check("sugerencias pintadas", (await page.locator("#sugerencias .sugerencia").count()) >= 3);

  const titulo = await page.textContent("#verdictTitle");
  check("veredicto coherente con el caso", /agota|fuga/i.test(titulo), titulo);

  console.log("\n=== TRAZA TECNICA ===");
  await page.click("#trazaBox summary");
  await page.waitForTimeout(250);
  check("traza abierta", await page.locator("#trazaBox[open]").count() === 1);
  check("herramientas listadas", (await page.locator(".traza-item").count()) >= 2);
  check("regla citada", (await page.textContent(".traza-regla")).includes("Regla"));

  console.log("\n=== MODAL DE DETALLE ===");
  await page.locator("#hallazgos .hallazgo").first().click();
  await page.waitForTimeout(350);
  check("modal abierto", await page.isVisible("#modalBackdrop"));
  check("modal con contenido", (await page.textContent("#modalBody")).trim().length > 60);
  await page.click("#modalClose");
  await page.waitForTimeout(250);
  check("modal cerrado", !(await page.isVisible("#modalBackdrop")));

  console.log("\n=== CHAT ===");
  await page.fill("#chatInput", "¿Cuánto cotizo a la CASS?");
  await page.click(".btn-send");
  await page.waitForTimeout(1400);
  check("mensaje de usuario", (await page.locator(".msg.user").count()) === 1);
  check("respuesta del bot", (await page.locator(".msg.bot").count()) >= 1);
  const respuesta = await page.textContent(".msg.bot");
  check("respuesta con regla aplicada", respuesta.includes("Regla aplicada"),
    respuesta.slice(0, 70));
  check("respuesta con numero", /\d/.test(respuesta));

  console.log("\n=== SUGERENCIA RAPIDA ===");
  const antes = await page.locator(".msg.bot").count();
  await page.locator("#sugerencias .sugerencia").first().click();
  await page.waitForTimeout(1400);
  check("nueva respuesta anadida", (await page.locator(".msg.bot").count()) > antes);

  console.log("\n=== CAMBIO DE IDIOMA ===");
  await page.click("#langSwitch");
  await page.waitForTimeout(250);
  check("idioma cambiado", (await page.getAttribute("html", "lang")) === "ca");
  check("texto traducido", (await page.textContent("#btnAnalizar")).includes("Analitzar"));
  await page.click("#langSwitch");
  await page.waitForTimeout(200);
  check("tercer idioma", (await page.getAttribute("html", "lang")) === "en");
  await page.click("#langSwitch");
  await page.waitForTimeout(200);
  check("vuelve a español", (await page.getAttribute("html", "lang")) === "es");

  console.log("\n=== REINICIO ===");
  await page.click("#btnReiniciar");
  await page.waitForTimeout(400);
  check("vuelve al paso 1", await page.isVisible("#stepContexto"));
  check("campos limpios", (await page.inputValue("#rentaNeta")) === "");
  check("chat vaciado", (await page.locator(".msg").count()) === 0);

  console.log("\n=== RESPONSIVE (desktop) ===");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForTimeout(300);
  check("sin scroll horizontal en desktop",
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));

  console.log("\n=== ERRORES JS ===");
  check("ningun error de JavaScript", erroresJS.length === 0,
    erroresJS.slice(0, 3).join(" | "));

  await page.screenshot({ path: path.join(process.env.FRONT_SHOT_DIR || "/tmp", "frontend_mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.click('.opcion[data-perfil="contratar"]');
  await page.click("#btnAnalizar");
  await page.waitForSelector("#stepResultado:not([hidden])", { timeout: 15000 });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(process.env.FRONT_SHOT_DIR || "/tmp", "frontend_desktop.png"), fullPage: true });

  await browser.close();

  console.log("\n" + "=".repeat(62));
  if (fallos.length) {
    console.log(`FALLOS: ${fallos.length} de ${n}`);
    fallos.forEach((f) => console.log("  -", f));
    process.exit(1);
  }
  console.log(`TODOS LOS TESTS DEL FRONTEND PASAN (${n})`);
  console.log("=".repeat(62));
})().catch((e) => {
  console.error("ERROR:", e);
  process.exit(1);
});
