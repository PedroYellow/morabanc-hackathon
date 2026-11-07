// Captura la web REAL de MoraBanc (welcomeandorra.com) para el video.
// El video muestra el producto de verdad, no un mockup.
//
// Salida: pitch/rec/*.png  (1920x1080)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = '/data/projects/morabanc_hackathon/pitch/rec';
const URL = 'https://welcomeandorra.com/';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));

  const marca = {};
  let n = 0;
  const shot = async (nombre) => {
    n += 1;
    const f = path.join(OUT, `f${String(n).padStart(3, '0')}.png`);
    await p.screenshot({ path: f });
    marca[nombre] = n;
    console.log(`  ${nombre}: frame ${n}`);
  };

  await p.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
  await p.waitForTimeout(2500);
  await shot('inicio');

  // --- El caso "contratar": el pitch ---
  await p.click('button[data-perfil="contratar"]');
  await p.waitForTimeout(1200);
  await shot('perfil_cargado');

  await p.click('#btnAnalizar');
  await p.waitForTimeout(1000);
  await shot('analizando');

  // El motor tarda un momento en la demo: espera a que aparezcan las metricas
  await p.waitForSelector('.metrica-valor, .mvalor', { timeout: 45000 }).catch(() => {});
  await p.waitForTimeout(3500);
  await shot('resultado');

  // Scroll al veredicto
  await p.evaluate(() => {
    const v = document.querySelector('.veredicto, #veredicto');
    if (v) v.scrollIntoView({ block: 'center' });
  });
  await p.waitForTimeout(900);
  await shot('veredicto');

  // --- Modo presentacion: la vista de proyector ---
  await p.evaluate(() => window.scrollTo(0, 0));
  await p.waitForTimeout(500);
  const btn = await p.$('#btnPresentacion');
  if (btn) {
    await btn.click();
    await p.waitForTimeout(2200);
    await shot('presentacion');
    await p.keyboard.press('Escape');
    await p.waitForTimeout(900);
  }

  // --- Las fugas de gasto ---
  await p.evaluate(() => {
    const f = document.querySelector('#fugas, .fugas, [id*=fuga]');
    if (f) f.scrollIntoView({ block: 'center' });
  });
  await p.waitForTimeout(900);
  await shot('fugas');

  console.log('\n  MARCAS:', JSON.stringify(marca));
  console.log('  errores JS:', errs.length, errs.slice(0, 3));
  fs.writeFileSync(path.join(OUT, 'marcas.json'), JSON.stringify(marca, null, 2));
  await b.close();
})();
