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
  // Sin resultados no hay nada que presentar: el boton no debe verse.
  check("el boton de presentacion esta oculto al inicio",
    !(await page.locator("#btnPresentacion").isVisible()));
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
  // El titular es proporcional al problema: con un hueco de 0,31 € NO es
  // "Tu caja se agota" (eso lo desmonta el jurado en una pregunta), sino
  // "Tu caja va justa".
  check("veredicto coherente con el caso",
    /agota|va justa|se queda corta|fuga/i.test(titulo), titulo);
  check("el titular del veredicto no es alarmista con un hueco minimo",
    !/se agota/.test(titulo) || !/0,31/.test(titulo),
    titulo);

  // --- Los 4 fixes de la revision del pitch ---------------------------
  const etiquetasMetricas = await page.evaluate(() =>
    Array.from(document.querySelectorAll("#verdictMetrics .metric-label")).map(
      (e) => e.innerText.trim()
    )
  );
  check("la metrica del flujo dice ANUAL (no mensual)",
    etiquetasMetricas.some((t) => /FLUJO ANUAL/i.test(t)) &&
    !etiquetasMetricas.some((t) => /FLUJO MENSUAL/i.test(t)),
    etiquetasMetricas.join(" | "));

  const hint = await page.textContent(".field-hint").catch(() => "");
  check("el campo de renta neta explica que es lo que queda tras gastos",
    /tras gastos/i.test(hint || ""), (hint || "").slice(0, 90));

  const titHallazgos = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".hallazgo-titulo")).map((e) => e.innerText.trim())
  );
  check("el titulo del crossover no esta cortado",
    !titHallazgos.some((t) => /art\.$/.test(t)),
    titHallazgos[0] || "(ninguno)");
  check("el titulo del crossover se ve completo",
    titHallazgos.some((t) => /Bonificacion IRPF art\. 46/.test(t)),
    titHallazgos[0] || "(ninguno)");

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

  console.log("\n=== MODO PRESENTACION (proyector) ===");
  // Vista grande para el proyector. Si se rompe, en el dia del hackathon se
  // queda sin pantalla grande en mitad del pitch.
  check("el boton de presentacion aparece con resultados",
    await page.locator("#btnPresentacion").isVisible());

  await page.click("#btnPresentacion");
  await page.waitForTimeout(600);
  check("la vista de presentacion se abre",
    await page.locator("#presentacion").isVisible());
  check("la cabecera de la app se oculta en presentacion",
    await page.evaluate(() => getComputedStyle(document.querySelector(".topbar")).display === "none"));

  const pres = await page.evaluate(() => {
    const el = document.querySelector("#presentacion");
    const r = el.getBoundingClientRect();
    const svg = document.querySelector("#presGrafico");
    const sr = svg.getBoundingClientRect();
    return {
      top: r.top, left: r.left, w: r.width, h: r.height,
      scrollH: el.scrollHeight,
      innerH: window.innerHeight,
      metrics: document.querySelectorAll("#presMetrics .presentacion-metric").length,
      paths: svg.querySelectorAll("path").length,
      title: document.querySelector("#presTitle").textContent.trim(),
      svgH: sr.height,
    };
  });
  // La vista tiene que ocupar el viewport EXACTO: si el contenedor esta
  // dentro de un <section> con animacion, position:fixed se referencia a ese
  // contexto y la vista aparece desplazada (solo se ve el grafico).
  check("la presentacion ocupa el viewport", pres.top === 0 && pres.left === 0,
    `top=${pres.top} left=${pres.left}`);
  check("la presentacion no hace scroll", pres.scrollH <= pres.innerH + 2,
    `${pres.scrollH} vs ${pres.innerH}`);
  check("el veredicto aparece en grande", pres.title.length > 5, pres.title);
  check("se muestran las 4 metricas", pres.metrics === 4, pres.metrics);
  check("el grafico se dibuja", pres.paths >= 2, pres.paths);
  check("el grafico tiene altura razonable", pres.svgH > 100 && pres.svgH < 600, pres.svgH);

  // Escape vuelve al resultado
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  check("Escape cierra la presentacion", !(await page.locator("#presentacion").isVisible()));
  check("la cabecera de la app vuelve", await page.evaluate(() =>
    getComputedStyle(document.querySelector(".topbar")).display !== "none"));

  console.log("\n=== IDENTIDAD DE MARCA MORABANC ===");
  // El front tiene que parecerse al banco: navy #0a3550, gold #f1c657 y el
  // logo real. Si alguien cambia la paleta, esto lo detecta.
  const marca = await page.evaluate(() => {
    const cs = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el).getPropertyValue(prop).trim() : null;
    };
    return {
      navy: cs(".topbar", "background-color"),
      gold: cs(".btn-primary", "background-color"),
      bodyBg: cs("body", "background-color"),
      txt: cs("body", "color"),
      cardBg: cs(".card", "background-color"),
      logoSrc: (document.querySelector(".brand-logo") || {}).src || "",
      logoVisible: (() => {
        const el = document.querySelector(".brand-logo");
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 40 && r.height > 8;
      })(),
    };
  });
  // El navy de MoraBanc es #0a3550 = rgb(10, 53, 80)
  check("la cabecera usa el navy de marca", marca.navy === "rgb(10, 53, 80)", marca.navy);
  // El gold de marca es #f1c657 = rgb(241, 198, 87)
  check("el boton principal usa el gold de marca", marca.gold === "rgb(241, 198, 87)", marca.gold);
  check("el fondo es claro (no dark)", marca.bodyBg === "rgb(244, 247, 250)", marca.bodyBg);
  check("el texto es oscuro sobre fondo claro", marca.txt === "rgb(33, 37, 41)", marca.txt);
  check("las cards son blancas", marca.cardBg === "rgb(255, 255, 255)", marca.cardBg);
  check("el logo real de MoraBanc esta cargado",
    marca.logoSrc.includes("logo-morabanc.svg"), marca.logoSrc);
  check("el logo se ve (no collapsed)", marca.logoVisible === true);

  console.log("\n=== FORMATO DE LOS NUMEROS (europeo) ===");
  // El front se ve en la sala el dia del hackathon: "4.267,05 €" se lee como
  // una cuenta; "4267.05 €" se lee como un dato de maquina. El build de
  // Chromium de este entorno va con ICU recortado, asi que el separador de
  // millares se pone a mano en el codigo (no con toLocaleString).
  const metricas = await page.locator("#verdictMetrics .metric-value").allTextContents();
  const conMiles = metricas.filter((m) => /\d\.\d{3}/.test(m));
  check("alguna metrica lleva separador de millares", conMiles.length > 0,
    metricas.join(" | "));
  check("ninguna metrica usa formato anglosaxon",
    !metricas.some((m) => /\d+\.\d{2}(?!\d)/.test(m)), metricas.join(" | "));
  // El signo va DELANTE: "-4.267,05 €". Un "-4.267,05" con el menos
  // pegado al numero por detras ("4.267,05-") seria un error de formato.
  check("el signo va delante del numero",
    !metricas.some((m) => /\d[\d.]*,\d{2}\s*€\s*-/.test(m)), metricas.join(" | "));

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


  console.log("\n=== SISTEMA DE DISENO (Lexicon) ===");
  // Se aplica la ESTRUCTURA de Lexicon (design systems one / design.liferay.com)
  // manteniendo la identidad corporativa real de MoraBanc (navy + gold).
  const estilos = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    const card = document.querySelector(".card");
    const opcion = document.querySelector(".opcion");
    const input = document.querySelector('input[type="text"]');
    return {
      space1: cs.getPropertyValue("--space-1").trim(),
      space3: cs.getPropertyValue("--space-3").trim(),
      space4: cs.getPropertyValue("--space-4").trim(),
      space5: cs.getPropertyValue("--space-5").trim(),
      radius: cs.getPropertyValue("--radius").trim(),
      radiusCard: cs.getPropertyValue("--radius-card").trim(),
      textBody: cs.getPropertyValue("--text-body").trim(),
      textSectionDivider: cs.getPropertyValue("--text-section-divider").trim(),
      lhBody: cs.getPropertyValue("--lh-body").trim(),
      lhHeading: cs.getPropertyValue("--lh-heading").trim(),
      cardRadius: card ? getComputedStyle(card).borderRadius : "",
      cardShadow: card ? getComputedStyle(card).boxShadow : "",
      opcionRadius: opcion ? getComputedStyle(opcion).borderRadius : "",
      opcionShadow: opcion ? getComputedStyle(opcion).boxShadow : "",
      inputRadius: input ? getComputedStyle(input).borderRadius : "",
      fontFamily: getComputedStyle(document.body).fontFamily,
    };
  });

  // Espaciado sobre una base de 8px, con sub-unidad de 4px.
  check("el espaciado usa una base de 8px con sub-unidad de 4px",
    estilos.space1 === "4px" && estilos.space3 === "16px" &&
    estilos.space4 === "24px" && estilos.space5 === "32px",
    `${estilos.space1}/${estilos.space3}/${estilos.space4}/${estilos.space5}`);
  check("el radio por defecto es de 8px", estilos.radius === "8px", estilos.radius);
  check("el radio de tarjeta es de 16px", estilos.radiusCard === "16px", estilos.radiusCard);
  check("la escala tipografica de Lexicon esta aplicada",
    estilos.textBody === "16px" && estilos.textSectionDivider === "14px",
    `${estilos.textBody}/${estilos.textSectionDivider}`);
  check("los interlineados son 1.25 en titulos y 1.5 en cuerpo",
    estilos.lhHeading === "1.25" && estilos.lhBody === "1.5",
    `${estilos.lhHeading}/${estilos.lhBody}`);

  // Lexicon: sin sombra en reposo, el relieve lo dan los bordes.
  check("las tarjetas no tienen sombra en reposo",
    estilos.cardShadow === "none", estilos.cardShadow);
  check("las opciones no tienen sombra en reposo",
    estilos.opcionShadow === "none", estilos.opcionShadow);

  // Radios aplicados en los componentes reales.
  check("las tarjetas usan el radio de 16px",
    estilos.cardRadius.includes("16px"), estilos.cardRadius);
  check("las opciones usan el radio de 16px",
    estilos.opcionRadius.includes("16px"), estilos.opcionRadius);
  check("los campos de texto usan el radio de 8px",
    estilos.inputRadius.includes("8px"), estilos.inputRadius);

  // Pila nativa del sistema: sin webfonts (pesa 0 KB y sin salto de fuente).
  check("la tipografia es la pila nativa del sistema",
    estilos.fontFamily.includes("system-ui") && !estilos.fontFamily.includes("Source Sans"),
    estilos.fontFamily.slice(0, 80));

  // La IDENTIDAD de MoraBanc se mantiene: Lexicon aporta estructura, no paleta.
  const identidad = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    return {
      navy: cs.getPropertyValue("--navy").trim(),
      gold: cs.getPropertyValue("--gold").trim(),
    };
  });
  check("se mantiene la identidad corporativa de MoraBanc (navy y gold)",
    identidad.navy === "#0a3550" && identidad.gold === "#f1c657",
    `${identidad.navy}/${identidad.gold}`);


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

  console.log("\n=== MODO PRESENTACION ===");
  await page.click("#btnPresentacion");
  await page.waitForTimeout(1200);
  const vistaPres = await page.evaluate(() => {
    const cont = document.querySelector(".presentacion");
    const r = cont ? cont.getBoundingClientRect() : null;
    const vals = Array.from(document.querySelectorAll(".presentacion-metric-value"));
    return {
      top: r ? Math.round(r.top) : null,
      bottom: r ? Math.round(r.bottom) : null,
      ventana: window.innerHeight,
      metricas: vals.map((v) => ({
        texto: v.textContent.trim(),
        ancho: Math.round(v.getBoundingClientRect().width),
        scroll: v.scrollWidth,
      })),
    };
  });
  check("la vista de presentacion ocupa exactamente la pantalla",
    vistaPres.top === 0 && vistaPres.bottom <= vistaPres.ventana + 2,
    `${vistaPres.top}-${vistaPres.bottom} en ${vistaPres.ventana}`);
  check("las metricas de presentacion no se salen de su tarjeta",
    vistaPres.metricas.every((m) => m.scroll <= m.ancho + 1),
    JSON.stringify(vistaPres.metricas.map((m) => `${m.texto}:${m.scroll}/${m.ancho}`)));
  check("hay 4 metricas en la presentacion",
    vistaPres.metricas.length === 4,
    `${vistaPres.metricas.length} metricas`);
  // La vista de presentacion es position:fixed y TAPA el boton, asi que
  // no se puede cerrar con un click: se cierra con Escape.
  await page.keyboard.press("Escape");
  await page.waitForTimeout(600);
  check("Escape cierra la vista de presentacion",
    await page.evaluate(() => !document.body.classList.contains("presentacion-activa")));


  // ---------------------------------------------------------------------
  // El texto de los hallazgos NO se puede truncar
  // ---------------------------------------------------------------------
  // Un parrafo de una regla legal cortado a media frase ("...y la
  // bonificacio de") parece un bug en pantalla y en una sala. El motor
  // redacta el texto completo y el front lo muestra entero.
  // El test anterior dejo la pagina en la vista de resultado (o en modo
  // presentacion). Los botones de perfil viven en la vista inicial, asi
  // que hay que volver a cargar la pagina.
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  await page.click('button[data-perfil="contratar"]');
  await page.waitForTimeout(700);
  await page.click("#btnAnalizar");
  await page.waitForTimeout(4000);

  const descs = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".hallazgo-desc")).map(
      (e) => e.innerText.trim()
    )
  );
  check("hay descripciones de hallazgos", descs.length > 0, `${descs.length} descripciones`);
  check(
    "ninguna descripcion esta truncada (no acaba a media frase)",
    descs.every((t) => t.length > 0 && /[.€!?)]\s*$/.test(t)),
    descs
      .filter((t) => t.length > 0 && !/[.€!?)]\s*$/.test(t))
      .map((t) => t.slice(-40))
      .join(" | ")
  );
  check(
    "la bonificacion se muestra completa",
    descs.some((t) => /bonificaci/.test(t) && t.length > 200),
    descs.filter((t) => /bonificaci/.test(t)).map((t) => t.length).join(",")
  );

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
