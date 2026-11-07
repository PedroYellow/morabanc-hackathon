/* ============================================================
   Asesor Financiero IA — MoraBanc
   Cliente del motor de decisiones.

   REGLA: este JS NO calcula nada. Solo pide, muestra y dibuja.
   Todos los numeros vienen del motor (API) o, en modo demo local,
   del mismo motor ejecutado en un worker local.
   ============================================================ */

(function () {
  "use strict";

  // ---------------------------------------------------------------
  // Config
  // ---------------------------------------------------------------
  const CFG = {
    // Se inyecta al desplegar (ver terraform output frontend_url_config).
    apiUrl: window.__API_URL__ || "",
    cognitoDomain: window.__COGNITO_DOMAIN__ || "",
    cognitoClientId: window.__COGNITO_CLIENT_ID__ || "",
    region: window.__AWS_REGION__ || "eu-west-1",
    // Modo demo: usa un motor local en un Web Worker (mismos numeros).
    modoDemo: !window.__API_URL__,
  };

  const PERFILES_DEMO = {
    freelance: {
      etiqueta: "Freelance de servicios",
      csv: "data/demo_freelance.csv",
      saldo: 8500, renta: 30000, margen: 0.70,
      actividad: "Freelance de servicios",
    },
    contratar: {
      etiqueta: "Freelancer con nómina",
      csv: "data/demo_freelancer_contratar.csv",
      saldo: 3200, renta: 28000, margen: 0.70,
      actividad: "Freelancer de servicios",
    },
    comercio: {
      etiqueta: "Comercio con tienda",
      csv: "data/demo_comercio.csv",
      saldo: 14200, renta: 45000, margen: 0.35,
      actividad: "Comercio con tienda local",
    },
    cierre: {
      etiqueta: "Freelancer que siguió el consejo",
      csv: "data/demo_freelancer_cierre.csv",
      saldo: 6100, renta: 30000, margen: 0.70,
      actividad: "Freelance de servicios",
      // Fecha en la que el motor dio el consejo: 1 de julio de 2026.
      // El cierre del bucle evalua los movimientos posteriores a esa fecha.
      fechaConsejo: "2026-07-01",
    },
  };

  const SUGERENCIAS = {
    freelance: [
      "¿Cuánto se me está escapando cada mes?",
      "¿Cuántos meses me aguanto en caja?",
      "¿Cuánto cotizo a la CASS?",
      "¿Cuándo salta mi tramo de cotización?",
      "¿Cuánto me conviene facturar?",
    ],
    contratar: [
      "¿Puedo contratar a alguien a 2.400 euros?",
      "¿Cuánto se me está escapando cada mes?",
      "¿Cuántos meses me aguanto en caja?",
      "¿Cuánto me conviene facturar?",
    ],
    comercio: [
      "¿Cuánto se me está escapando cada mes?",
      "¿Cuánto cotizo a la CASS?",
      "¿Cuánto me conviene facturar?",
      "¿Cuándo salta mi tramo de cotización?",
    ],
    cierre: [
      "¿Hiciste caso con mis consejos?",
      "¿Cuánto se me está escapando cada mes?",
      "¿Cuánto cotizo a la CASS?",
      "¿Cuántos meses me aguanto en caja?",
    ],
  };

  // ---------------------------------------------------------------
  // i18n (ES / CA / EN)
  // ---------------------------------------------------------------
  const I18N = {
    es: {
      tituloContexto: "Tu situación financiera",
      subtituloContexto: "Empezamos por lo básico: tus cuentas y tus ingresos.",
      tusDatos: "Tus datos fiscales",
      tusDatosHint: "Con esto calculamos tu CASS, tu IRPF y tu IGI con la normativa andorrana.",
      analizar: "Analizar mi situación",
      diagnostico: "Diagnóstico",
      hallazgos: "Lo que hemos encontrado",
      cajaMes: "Tu caja mes a mes",
      preguntame: "Pregúntame lo que quieras",
      razonamiento: "Ver el razonamiento y las reglas aplicadas",
      reiniciar: "← Empezar de nuevo",
      reglaAplicada: "Regla aplicada",
      cargando: "Analizando tu situación…",
      errorDemo: "No se pudo cargar la demo. ¿Pruebas con la cuenta de demostración?",
    },
    ca: {
      tituloContexto: "La teva situació financera",
      subtituloContexto: "Comencem pel bàsic: els teus comptes i els teus ingressos.",
      tusDatos: "Les teves dades fiscals",
      tusDatosHint: "Amb això calculem la teva CASS, l'IRPF i l'IGI amb la normativa andorrena.",
      analizar: "Analitzar la meva situació",
      diagnostico: "Diagnòstic",
      hallazgos: "Allò que hem trobat",
      cajaMes: "La teva caixa mes a mes",
      preguntame: "Pregunta'm el que vulguis",
      razonamiento: "Mostra el raonament i les regles aplicades",
      reiniciar: "← Torna a començar",
      reglaAplicada: "Regla aplicada",
      cargando: "Analitzant la teva situació…",
      errorDemo: "No s'ha pogut carregar la demo. Proves amb el compte de demostració?",
    },
    en: {
      tituloContexto: "Your financial situation",
      subtituloContexto: "Let's start with the basics: your accounts and your income.",
      tusDatos: "Your tax details",
      tusDatosHint: "We use this to calculate your CASS, IRPF and IGI with Andorran regulations.",
      analizar: "Analyse my situation",
      diagnostico: "Diagnosis",
      hallazgos: "What we found",
      cajaMes: "Your cash month by month",
      preguntame: "Ask me anything",
      razonamiento: "Show the reasoning and the rules applied",
      reiniciar: "← Start over",
      reglaAplicada: "Rule applied",
      cargando: "Analysing your situation…",
      errorDemo: "Couldn't load the demo. Try the demo account?",
    },
  };

  let lang = "es";
  const t = (k) => (I18N[lang] && I18N[lang][k]) || I18N.es[k] || k;

  // ---------------------------------------------------------------
  // Estado
  // ---------------------------------------------------------------
  const state = {
    perfil: null,
    contexto: null,      // { saldo, renta, margen, actividad, movimientos }
    ultimoAnalisis: null,
    chatAbierto: false,
  };

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  // ---------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------
  // Formato de euros: separador de millares con punto y decimal con coma
  // (es-ES / en-GB segun el idioma de la interfaz).
  //
  // NO se usa toLocaleString para los millares: el build de Chromium de
  // este entorno va con ICU recortado y devuelve "4267,05" en vez de
  // "4.267,05" (y lo mismo con el signo delante). Es un problema del
  // entorno, no del codigo, pero el front se ve en la sala el dia del
  // hackathon: si el navegador del movil tiene ICU completo, mejor, pero
  // no puede ser la unica garantia. Por eso el separador de millares se
  // pone a mano y toLocaleString solo se encarga de los decimales.
  function separarMillares(texto, sep) {
    const neg = texto.startsWith("-");
    const limpio = neg ? texto.slice(1) : texto;
    const partes = limpio.split(".");
    const entero = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, sep);
    return (neg ? "-" : "") + (partes.length > 1 ? entero + "." + partes[1] : entero);
  }

  function eur(v, dec) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    const n = Number(v);
    const d = dec === undefined ? 0 : dec;
    const sep = lang === "en" ? "," : ".";
    const texto = Math.abs(n).toFixed(d);
    const partes = texto.split(".");
    const entero = separarMillares(partes[0], sep);
    const signo = n < 0 ? "-" : "";
    return signo + entero + (partes.length > 1 ? "," + partes[1] : "") + " €";
  }

  function num(v, dec) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    const n = Number(v);
    const d = dec || 0;
    const sep = lang === "en" ? "," : ".";
    const texto = Math.abs(n).toFixed(d);
    const partes = texto.split(".");
    const entero = separarMillares(partes[0], sep);
    return (n < 0 ? "-" : "") + entero + (partes.length > 1 ? "," + partes[1] : "");
  }

  function toast(msg, tipo) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast" + (tipo ? " " + tipo : "");
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.hidden = true; }, 3600);
  }

  /** Convierte **markdown** a HTML seguro (solo negritas y saltos de linea). */
  function md(texto) {
    if (!texto) return "";
    const esc = String(texto)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return esc
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\n\n/g, "</p><p>")
      .replace(/\n/g, "<br>");
  }

  // ---------------------------------------------------------------
  // API
  // ---------------------------------------------------------------
  async function preguntar(pregunta, contexto) {
    const cuerpo = {
      pregunta,
      empresa_id: state.perfil || "demo",
      saldo_actual: contexto.saldo,
      renta_neta_anual: contexto.renta,
      margen_bruto: contexto.margen,
      actividad: contexto.actividad,
      extracto_csv: contexto.csv || undefined,
      // Fecha del ultimo consejo: el motor la usa para el cierre del bucle.
      fecha_consejo: contexto.fechaConsejo || undefined,
    };

    const resp = await fetch(CFG.apiUrl + "/preguntar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || ("HTTP " + resp.status));
    }
    return resp.json();
  }

  // ---------------------------------------------------------------
  // Modo demo: datos precalculados por el motor real (Python)
  // ---------------------------------------------------------------
  // El JSON lo genera frontend/generar_demo_data.py ejecutando el MISMO
  // motor que corre en AWS. Aqui no se calcula nada: se muestra lo que
  // el motor ya dijo. Los numeros son identicos en ambos modos.
  let DEMO = null;

  async function cargarDemo() {
    if (DEMO) return DEMO;
    const resp = await fetch("data/demo_data.json");
    if (!resp.ok) throw new Error("No se pudo cargar data/demo_data.json");
    DEMO = await resp.json();
    return DEMO;
  }

  function fmtEuro(v, dec) {
    return eur(v, dec);
  }

  /** Enruta una pregunta a la parte del JSON que le corresponde. */
  async function preguntarDemo(pregunta, contexto) {
    const data = await cargarDemo();
    const perfil = data[state.perfil] || data.freelance;
    const p = pregunta.toLowerCase();

    const herramienta = (nombre) => ({ tool: nombre, input: {}, resultado: null, regla: "" });

    let salida;
    if (/fuga|escap|suscrip|duplicad|gasto|ahorr/.test(p)) {
      salida = {
        tool: "detectar_fugas",
        resultado: perfil.fugas,
        regla: "Suscripciones: mismo concepto e importe con frecuencia mensual >= 0,8. " +
                "Duplicados: mismo importe y concepto en <= 5 dias. " +
                "Deriva: gasto de una categoria que crece > 15% en 3 meses.",
      };
    } else if (/caja|quiebre|aguanto|runway|meses/.test(p)) {
      salida = {
        tool: "proyectar_caja",
        resultado: perfil.proyeccion,
        regla: "Proyeccion determinista mes a mes sobre el flujo medio real. " +
                "El quiebre se marca cuando el saldo pasa a negativo.",
      };
    } else if (/crossover|umbral|salta|tramo|punto/.test(p)) {
      salida = {
        tool: "detectar_crossover_fiscal",
        resultado: perfil.crossover,
        regla: "Salt de tramo CASS per renda neta (40.000 EUR -> 125%, " +
                "50.000 EUR -> 137,5%) i topament de la bonificacio IRPF art. 46 en 40.000 EUR.",
      };
    } else if (/cotiz|cass|seguridad social/.test(p)) {
      salida = {
        tool: "tramo_cass",
        resultado: perfil.cass,
        regla: "CASS " + perfil.cass.tramo + ". Base global 2.672,52 EUR (Decret 28/2026), " +
                "tipo total 22% (10% rama general + 12% jubilacion).",
      };
    } else if (/irpf|impuesto|tribut/.test(p)) {
      salida = {
        tool: "calcular_irpf",
        resultado: perfil.irpf,
        regla: "Llei 5/2014 de l'IRPF: art. 35 (minim personal 24.000 EUR), " +
                "art. 43 (tipus 10%), art. 46 (bonificacio 50% amb tope 800 EUR).",
      };
    } else if (/igi/.test(p)) {
      salida = {
        tool: "calcular_igi",
        resultado: perfil.igi,
        regla: "IGI 4,5% sobre el rendiment d'activitats economiques.",
      };
    } else if (/factur/.test(p)) {
      salida = {
        tool: "punto_optimo_facturacion",
        resultado: perfil.punto_optimo,
        regla: "Minimiza el coste fiscal total (CASS + IRPF) sobre la facturacion, " +
                "teniendo en cuenta que la CASS es un coste fijo por tramo que salta.",
      };
    } else if (/contratar|emplead|sueldo|brutos/.test(p)) {
      salida = {
        tool: "simular_contratacion",
        resultado: perfil.simular_contratacion,
        regla: "El coste del empleat es despesa deduible: no cambia la renta neta, " +
                "asi que la CASS i l'IRPF se mantienen. Lo que cambia es la caja.",
      };
    } else {
      salida = {
        tool: "analizar_tesoreria",
        resultado: perfil.tesoreria,
        regla: "Media aritmetica de ingresos y gastos sobre el periodo analizado, " +
                "normalizada a mensual.",
      };
    }

    return {
      respuesta: redactarDemo(pregunta, salida),
      herramientas: [salida],
      mock: true,
    };
  }

  /** Redaccion de ejemplo (en produccion la hace el LLM de Bedrock). */
  function redactarDemo(pregunta, h) {
    const r = h.resultado || {};

    if (h.tool === "detectar_fugas") {
      if (!r.n_fugas) {
        return "No he encontrado fugas claras en el periodo analizado.\n\n" +
               "**Regla aplicada:** " + h.regla;
      }
      const lineas = [
        "**He encontrado " + r.n_fugas + " fugas.** Recuperando lo que no usas: " +
        "**" + fmtEuro(r.recuperable_mensual, 2) + "/mes** (" +
        fmtEuro(r.recuperable_anual, 0) + "/año).", "",
      ];
      (r.fugas || []).slice(0, 4).forEach((f) => {
        lineas.push("- **" + f.descripcion.split(".")[0] + "** → " + f.accion_sugerida);
      });
      lineas.push("", "**Regla aplicada:** " + h.regla);
      return lineas.join("\n");
    }

    if (h.tool === "proyectar_caja") {
      return "**" + r.resumen + "**\n\nHorizonte: " + (r.meses || []).length +
             " meses.\n\n**Regla aplicada:** " + h.regla;
    }

    if (h.tool === "detectar_crossover_fiscal") {
      if (!r.existe) return r.detalle + "\n\n**Regla aplicada:** " + h.regla;
      return "**" + r.tipo + "**\n\n" + r.detalle + "\n\n**Regla aplicada:** " + h.regla;
    }

    if (h.tool === "tramo_cass") {
      return "**Tramo " + r.tramo + "** — cuota " + fmtEuro(r.cuota_mensual, 2) + "/mes (" +
             fmtEuro(r.cuota_anual, 0) + "/año). Base: " + fmtEuro(r.base_cotizacion, 2) + ".\n\n" +
             "**Regla aplicada:** " + h.regla;
    }

    if (h.tool === "calcular_irpf") {
      return "**IRPF: " + fmtEuro(r.cuota_total, 2) + "** (tipo efectivo " +
             num(r.tipo_efectivo, 2) + "%).\n\n**Regla aplicada:** " + h.regla;
    }

    if (h.tool === "calcular_igi") {
      return "**IGI: " + fmtEuro(r.cuota, 2) + "** (tipo 4,5%).\n\n**Regla aplicada:** " + h.regla;
    }

    if (h.tool === "punto_optimo_facturacion") {
      const bp = r.mejor_punto || {};
      return "**El punto optimo de facturacion esta alrededor de " +
             num(bp.renta_neta, 0) + " € de renta neta.**\n" +
             "Carga fiscal total: " + fmtEuro(bp.carga_total_anual, 2) + "/año (" +
             num(bp.efectivo_sobre_facturacion, 2) + "% de lo facturado).\n\n" +
             (r.nota || "") + "\n\n**Regla aplicada:** " + h.regla;
    }

    if (h.tool === "simular_contratacion") {
      return "**Contratar cuesta " + fmtEuro(r.coste_nuevo_empleado_anual, 2) + "/año.**\n\n" +
             "Necesitas facturar **" + fmtEuro(r.facturacion_adicional_para_cubrirlo, 2) +
             " adicionales** para cubrirlo con margen e IGI incluidos (de los cuales " +
             fmtEuro(r.igi_adicional, 2) + " son IGI).\n\n" +
             "**Regla aplicada:** " + h.regla;
    }

    // Tesoreria
    return "**Flujo neto: " + fmtEuro(r.flujo_neto, 2) + "** en el periodo analizado.\n" +
           "Ingresos: " + fmtEuro(r.ingresos_totales, 2) + " | Gastos: " +
           fmtEuro(r.gastos_totales, 2) + "\n" +
           "Media mensual: " + fmtEuro(r.ingresos_mes, 2) + " de ingresos, " +
           fmtEuro(r.gastos_mes, 2) + " de gastos.\n\n" +
           "**Regla aplicada:** " + h.regla;
  }

  // ---------------------------------------------------------------
  // Carga de datos
  // ---------------------------------------------------------------
  async function cargarExtractoDemo(ruta) {
    const resp = await fetch(ruta);
    if (!resp.ok) throw new Error("No se pudo cargar " + ruta);
    return resp.text();
  }

  // ---------------------------------------------------------------
  // Paso 1: seleccion de contexto
  // ---------------------------------------------------------------
  function inicializarOpciones() {
    $$("#opcionesInicio .opcion").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const modo = btn.dataset.modo;

        $$("#opcionesInicio .opcion").forEach((b) => b.classList.remove("selected"));
        btn.classList.add("selected");

        if (modo === "subir") {
          $("#uploadZone").hidden = false;
          $("#cardDatos").hidden = false;
          return;
        }

        const perfil = PERFILES_DEMO[btn.dataset.perfil];
        if (!perfil) return;

        $("#uploadZone").hidden = true;
        $("#cardDatos").hidden = false;

        // Rellenamos los campos con el perfil para que se vea el efecto
        $("#rentaNeta").value = perfil.renta;
        $("#margenBruto").value = Math.round(perfil.margen * 100);
        $("#saldoActual").value = perfil.saldo;
        $("#actividad").value = perfil.actividad;

        state.perfil = btn.dataset.perfil;
        state.contexto = {
          saldo: perfil.saldo,
          renta: perfil.renta,
          margen: perfil.margen,
          actividad: perfil.actividad,
          fechaConsejo: perfil.fechaConsejo || null,
          csv: null,
        };
      });
    });

    $("#fileInput").addEventListener("change", async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const texto = await file.text();
      state.perfil = "subido";
      state.contexto = Object.assign(state.contexto || {}, { csv: texto });
      $("#fileDropTitle").textContent = file.name;
      toast("Extracto cargado: " + num(file.size / 1024, 1) + " KB", "ok");
    });
  }

  // ---------------------------------------------------------------
  // Paso 2: analisis
  // ---------------------------------------------------------------
  async function analizar() {
    const btn = $("#btnAnalizar");
    const renta = parseFloat($("#rentaNeta").value);
    const margenPct = parseFloat($("#margenBruto").value);
    const saldo = parseFloat($("#saldoActual").value);
    const actividad = $("#actividad").value.trim();

    if (!renta || renta <= 0) {
      toast("Necesitamos tu renta neta anual", "error");
      $("#rentaNeta").focus();
      return;
    }

    const ctx = Object.assign({}, state.contexto || {}, {
      saldo: isNaN(saldo) ? 0 : saldo,
      renta,
      margen: (margenPct || 70) / 100,
      actividad: actividad || "Autónomo",
    });

    btn.disabled = true;
    btn.querySelector("span").textContent = t("cargando");

    try {
      const preguntas = [
        "¿Cuánto se me está escapando cada mes?",
        "¿Cuántos meses me aguanto en caja?",
        "¿Cuándo salta mi tramo de cotización?",
      ];

      const resultados = [];

      if (CFG.modoDemo) {
        // En modo demo los datos ya estan precalculados por el motor:
        // una sola carga y las tres lecturas salen de ahi.
        const data = await cargarDemo();
        const perfil = data[state.perfil] || data.freelance;

        const map = {
          "¿Cuánto se me está escapando cada mes?": "detectar_fugas",
          "¿Cuántos meses me aguanto en caja?": "proyectar_caja",
          "¿Cuándo salta mi tramo de cotización?": "detectar_crossover_fiscal",
        };

        for (const p of preguntas) {
          const tool = map[p];
          const r = await preguntarDemo(p, ctx);
          // Anadimos tambien el tramo CASS y el flujo, que la pantalla usa.
          if (tool === "detectar_fugas") {
            r.herramientas.push({
              tool: "tramo_cass", input: {}, resultado: perfil.cass,
              regla: "CASS " + perfil.cass.tramo + ". Base global 2.672,52 EUR (Decret 28/2026), tipo total 22%.",
            });
            r.herramientas.push({
              tool: "analizar_tesoreria", input: {}, resultado: perfil.tesoreria,
              regla: "Media aritmetica de ingresos y gastos sobre el periodo analizado, normalizada a mensual.",
            });
          }
          resultados.push({ pregunta: p, ...r });
        }
      } else {
        // Modo real: el extracto se sube a la API y el agente elige las tools.
        let csv = ctx.csv;
        if (!csv && state.perfil && PERFILES_DEMO[state.perfil]) {
          csv = await cargarExtractoDemo(PERFILES_DEMO[state.perfil].csv);
        }
        ctx.csv = csv;

        for (const p of preguntas) {
          const r = await preguntar(p, ctx);
          resultados.push({ pregunta: p, ...r });
        }
      }

      state.ultimoAnalisis = resultados;
      mostrarPaso(2);                 // primero hacemos visible el paso 2
      pintarResultado(resultados, ctx);  // luego dibujamos (el SVG ya tiene ancho)
      redibujarGrafico();
    } catch (err) {
      console.error(err);
      toast((err && err.message) || "Error inesperado", "error");
    } finally {
      btn.disabled = false;
      btn.querySelector("span").textContent = t("analizar");
    }
  }

  function mostrarPaso(n) {
    $("#stepContexto").hidden = n !== 1;
    $("#stepResultado").hidden = n !== 2;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------------------------------------------------------------
  // Pintado del resultado
  // ---------------------------------------------------------------
  function pintarResultado(resultados, ctx) {
    const porTool = {};
    resultados.forEach((r) => {
      (r.herramientas || []).forEach((h) => { porTool[h.tool] = h; });
    });

    // --- Veredicto ------------------------------------------------
    const fugas = porTool["detectar_fugas"];
    const caja = porTool["proyectar_caja"];
    const cross = porTool["detectar_crossover_fiscal"];

    const card = $("#verdictCard");
    const metrics = $("#verdictMetrics");
    metrics.innerHTML = "";

    let titulo = "Situación estable";
    let texto = "Tu caja aguanta el horizonte analizado. Igual merece la pena mirar dónde se te va el dinero cada mes.";
    let clase = "ok";

    if (fugas) {
      const r = fugas.resultado || {};
      if (r.n_fugas > 0) {
        titulo = `Hay ${r.n_fugas} ${r.n_fugas === 1 ? "fuga" : "fugas"} en tu cuenta`;
        texto = `Recuperando lo que no usas: ${eur(r.recuperable_mensual, 2)} al mes. Eso son ${eur(r.recuperable_anual, 0)} al año, sin facturar ni un euro más.`;
        clase = "warn";
      }
    }

    if (caja && caja.resultado && caja.resultado.mes_quiebre) {
      titulo = `Tu caja se agota en el mes ${caja.resultado.mes_quiebre}`;
      const ultimo = caja.resultado.ultimo_saldo_positivo;
      texto = `Al ritmo actual no llegas al final del horizonte. Tu último saldo cómodo es de ${eur(ultimo, 2)} ` +
              `y en el mes del quiebre te faltan ${eur(caja.resultado.deuda_en_quiebre, 2)}. ` +
              `Todavía estás a tiempo de corregirlo.`;
      clase = "warn";
    }

    card.className = "verdict-card " + clase;
    $("#verdictLabel").textContent = t("diagnostico");
    $("#verdictTitle").textContent = titulo;
    $("#verdictText").textContent = texto;

    // Métricas
    const cass = porTool["tramo_cass"];
    const flujo = porTool["analizar_tesoreria"];
    if (cass && cass.resultado && cass.resultado.cuota_mensual) {
      metrics.appendChild(metrica("CASS", eur(cass.resultado.cuota_mensual, 2) + "/mes",
        "tramo " + cass.resultado.tramo));
    }
    if (flujo && flujo.resultado && flujo.resultado.flujo_neto !== undefined) {
      const f = flujo.resultado.flujo_neto;
      metrics.appendChild(metrica("Flujo mensual", eur(f, 2), f >= 0 ? "ahorras" : "gastas",
        f >= 0 ? "pos" : "neg"));
    }
    if (caja && caja.resultado && caja.resultado.mes_quiebre) {
      metrics.appendChild(metrica("Quiebre de caja", "Mes " + caja.resultado.mes_quiebre,
        "se queda sin saldo", "neg"));
    }
    if (cross && cross.resultado && cross.resultado.existe) {
      metrics.appendChild(metrica("Próximo umbral", eur(cross.resultado.renta_punto, 0),
        "de renta neta · salta tu tramo"));
    }

    // --- Hallazgos ------------------------------------------------
    const cont = $("#hallazgos");
    cont.innerHTML = "";

    // El crossover va PRIMERO: es el insight que ningun ERP muestra.
    if (cross && cross.resultado && cross.resultado.existe) {
      const r = cross.resultado;
      cont.appendChild(tarjetaHallazgo({
        tipo: "crossover",
        destacado: true,
        descripcion: r.tipo === "Bonificacion IRPF art. 46 toca su techo de 800 €"
          ? "Bonificacion IRPF art. 46 toca su techo de 800 €"
          : r.tipo,
        detalle: r.detalle,
        importe_anual: r.delta_anual_cass,
        accion_sugerida: r.detalle,
        movimientos_involucrados: [],
        confianza: 1,
      }));
    }

    if (fugas && fugas.resultado && fugas.resultado.fugas) {
      fugas.resultado.fugas.slice(0, 4).forEach((f) => {
        cont.appendChild(tarjetaHallazgo(f));
      });
    }

    // --- Gráfico --------------------------------------------------
    const cardProy = $("#cardProyeccion");
    if (caja && caja.resultado && caja.resultado.meses) {
      cardProy.hidden = false;
      dibujarGrafico(caja.resultado.meses, caja.resultado);
    } else {
      cardProy.hidden = true;
    }

    // --- Sugerencias ----------------------------------------------
    const sug = $("#sugerencias");
    sug.innerHTML = "";
    const lista = SUGERENCIAS[state.perfil] || SUGERENCIAS.freelance;
    lista.forEach((p) => {
      const b = document.createElement("button");
      b.className = "sugerencia";
      b.textContent = p;
      b.addEventListener("click", () => enviarPregunta(p));
      sug.appendChild(b);
    });

    // --- Traza ----------------------------------------------------
    pintarTraza(resultados);
  }

  function metrica(label, valor, sub, clase) {
    const d = document.createElement("div");
    d.innerHTML =
      '<div class="metric-label">' + label + "</div>" +
      '<div class="metric-value' + (clase ? " " + clase : "") + '">' + valor + "</div>" +
      (sub ? '<div class="metric-sub">' + sub + "</div>" : "");
    return d;
  }

  function tarjetaHallazgo(f) {
    const b = document.createElement("button");
    b.className = "hallazgo" + (f.destacado ? " destacado" : "");
    // Iconos SVG inline: los emojis no renderizan en todos los sistemas.
    const iconos = {
      suscripcion:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round"><path d="M17 2l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>' +
        '<path d="M7 22l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>',
      cobro_duplicado:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 L22 20 L2 20 Z"/>' +
        '<path d="M12 10v4"/><circle cx="12" cy="17" r=".7" fill="currentColor"/></svg>',
      deriva_gasto:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M21 7v5h-5"/></svg>',
      crossover:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>' +
        '<circle cx="12" cy="12" r="1" fill="currentColor"/></svg>',
    };
    const icon = iconos[f.tipo] ||
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
      '<circle cx="12" cy="12" r="3"/></svg>';
    // Titulo: la primera frase COMPLETA (con punto final), no cortada a medias.
    const titulo = primeraFrase(f.descripcion || "");
    const cuerpo = f.destacado
      ? (f.detalle || f.accion_sugerida || "")
      : (f.accion_sugerida || "");
    // En las fugas, la descripcion ya explica: la accion va dentro. Evitamos
    // repetir el mismo texto dos veces seguidas.
    // Si el detalle repite el titulo, lo recortamos: no hay que decir dos veces
    // lo mismo en la misma tarjeta.
    let detalle = f.destacado ? cuerpo : (f.descripcion || "") + (cuerpo ? " " + cuerpo : "");
    if (!f.destacado && detalle.startsWith(titulo)) {
      detalle = detalle.slice(titulo.length).replace(/^[\s.·-]+/, "");
    }

    b.innerHTML =
      '<span class="hallazgo-icon">' + icon + "</span>" +
      '<span class="hallazgo-body">' +
        '<span class="hallazgo-titulo">' + escapar(titulo) + "</span>" +
        '<span class="hallazgo-desc">' + escapar(detalle.slice(0, 260)) + "</span>" +
      "</span>" +
      (f.importe_anual
        ? '<span class="hallazgo-amount">' + eur(f.importe_anual, 0) + "<small>/año</small></span>"
        : "");
    b.addEventListener("click", () => abrirModal(f));
    return b;
  }

  /** Primera frase completa (con su punto final), no cortada a medias. */
  function primeraFrase(texto) {
    const t = String(texto || "");
    const m = t.match(/^.*?[.!?](?=\s|$)/);
    return (m ? m[0] : t).trim();
  }

  function escapar(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---------------------------------------------------------------
  // Gráfico de caja (SVG puro, sin librerías)
  // ---------------------------------------------------------------
  /** Redibuja el grafico con los ultimos datos (el SVG depende del ancho real). */
  function redibujarGrafico() {
    if (!state.ultimoAnalisis) return;
    const caja = state.ultimoAnalisis
      .flatMap((r) => r.herramientas || [])
      .find((h) => h.tool === "proyectar_caja");
    if (caja && caja.resultado && caja.resultado.meses) {
      dibujarGrafico(caja.resultado.meses, caja.resultado);
    }
  }

  // Al cambiar el tamano (rotacion del movil, resize de ventana) el grafico
  // se redibuja: la fuente del SVG depende del ancho real.
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(redibujarGrafico, 180);
  });

  function dibujarGrafico(meses, resultado) {
    const svg = $("#graficoCaja");
    const W = 640, H = 240;

    // El viewBox se escala al ancho real del contenedor. Compensamos la fuente
    // y los grosores para que el grafico se lea igual de bien en movil (304px)
    // que en escritorio (780px).
    const anchoReal = svg.clientWidth || 320;
    const escala = anchoReal / W;
    const fs = Math.max(10, Math.min(24, 10.5 / escala));
    const lw = Math.max(1.8, 2.2 / escala);

    const padL = Math.max(44, 46 / escala);
    const padR = 14;
    const padT = 14;
    const padB = 26;

    svg.innerHTML = "";

    if (!meses || !meses.length) return;

    const vals = meses.map((m) => Number(m.saldo));
    const max = Math.max(0, ...vals);
    const min = Math.min(0, ...vals);
    const span = (max - min) || 1;
    const y = (v) => padT + (max - v) / span * (H - padT - padB);
    const x = (i) => padL + (i / Math.max(1, meses.length - 1)) * (W - padL - padR);

    // rejilla
    const ns = "http://www.w3.org/2000/svg";
    const pasos = [0, 0.25, 0.5, 0.75, 1];
   pasos.forEach((f) => {
      const v = min + span * f;
      const yy = y(v);
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", padL); line.setAttribute("x2", W - padR);
      line.setAttribute("y1", yy); line.setAttribute("y2", yy);
      line.setAttribute("stroke", f === 0 ? "#39435a" : "#1e2534");
      line.setAttribute("stroke-width", (1 / escala).toFixed(2));
      svg.appendChild(line);
      const tx = document.createElementNS(ns, "text");
      tx.setAttribute("x", padL - 8); tx.setAttribute("y", yy + 3.5);
      tx.setAttribute("text-anchor", "end");
      tx.setAttribute("fill", "#7c8699");
      tx.setAttribute("font-size", fs.toFixed(1));
      tx.setAttribute("font-weight", "500");
      tx.textContent = num(v, 0);
      svg.appendChild(tx);
    });

    // area
    let d = "M" + x(0) + " " + y(vals[0]);
    for (let i = 1; i < vals.length; i++) d += " L" + x(i) + " " + y(vals[i]);
    const areaD = d + " L" + x(vals.length - 1) + " " + y(min) + " L" + x(0) + " " + y(min) + " Z";

    const grad = document.createElementNS(ns, "linearGradient");
    grad.setAttribute("id", "gCaja");
    grad.setAttribute("x1", "0"); grad.setAttribute("y1", "0");
    grad.setAttribute("x2", "0"); grad.setAttribute("y2", "1");
    const s1 = document.createElementNS(ns, "stop");
    s1.setAttribute("offset", "0%"); s1.setAttribute("stop-color", "#14f195"); s1.setAttribute("stop-opacity", "0.28");
    const s2 = document.createElementNS(ns, "stop");
    s2.setAttribute("offset", "100%"); s2.setAttribute("stop-color", "#14f195"); s2.setAttribute("stop-opacity", "0");
    grad.appendChild(s1); grad.appendChild(s2);
    const defs = document.createElementNS(ns, "defs");
    defs.appendChild(grad);
    svg.appendChild(defs);

    const area = document.createElementNS(ns, "path");
    area.setAttribute("d", areaD);
    area.setAttribute("fill", "url(#gCaja)");
    svg.appendChild(area);

    // linea: verde hasta el quiebre, rojo despues
    const quieb = resultado && resultado.mes_quiebre ? resultado.mes_quiebre - 1 : vals.length;
    let d1 = "M" + x(0) + " " + y(vals[0]);
    for (let i = 1; i <= Math.min(quieb, vals.length - 1); i++) d1 += " L" + x(i) + " " + y(vals[i]);
    const l1 = document.createElementNS(ns, "path");
    l1.setAttribute("d", d1); l1.setAttribute("fill", "none");
    l1.setAttribute("stroke", "#14f195"); l1.setAttribute("stroke-width", lw.toFixed(2));
    l1.setAttribute("stroke-linejoin", "round"); l1.setAttribute("stroke-linecap", "round");
    svg.appendChild(l1);

    if (quieb < vals.length - 1) {
      let d2 = "M" + x(quieb) + " " + y(vals[quieb]);
      for (let i = quieb + 1; i < vals.length; i++) d2 += " L" + x(i) + " " + y(vals[i]);
      const l2 = document.createElementNS(ns, "path");
      l2.setAttribute("d", d2); l2.setAttribute("fill", "none");
      l2.setAttribute("stroke", "#ff6b6b"); l2.setAttribute("stroke-width", lw.toFixed(2));
      l2.setAttribute("stroke-linejoin", "round"); l2.setAttribute("stroke-linecap", "round");
      svg.appendChild(l2);
    }

    // eje X
    const n = vals.length;
    const paso = Math.ceil(n / 6);
    for (let i = 0; i < n; i += paso) {
      const tx = document.createElementNS(ns, "text");
      tx.setAttribute("x", x(i)); tx.setAttribute("y", H - 8);
      tx.setAttribute("text-anchor", "middle");
      tx.setAttribute("fill", "#6c7689");
      tx.setAttribute("font-size", fs.toFixed(1));
      tx.textContent = "M" + (i + 1);
      svg.appendChild(tx);
    }

    // leyenda
    const lg = $("#leyendaProyeccion");
    lg.innerHTML = "";
    if (quieb < vals.length - 1) {
      lg.innerHTML =
        '<span class="legend-item"><span class="legend-swatch" style="background:#14f195"></span>Con caja</span>' +
        '<span class="legend-item"><span class="legend-swatch" style="background:#ff6b6b"></span>En números rojos</span>';
    } else {
      lg.innerHTML = '<span class="legend-item"><span class="legend-swatch" style="background:#14f195"></span>Saldo de caja</span>';
    }

    // nota
    const nota = $("#notaProyeccion");
    if (resultado && resultado.resumen) {
      nota.innerHTML = "<strong>Resumen:</strong> " + escapar(resultado.resumen);
    }
  }

  // ---------------------------------------------------------------
  // Traza tecnica
  // ---------------------------------------------------------------
  function pintarTraza(resultados) {
    const body = $("#trazaBody");
    body.innerHTML = "";
    const vistos = new Set();

    resultados.forEach((r) => {
      (r.herramientas || []).forEach((h) => {
        if (vistos.has(h.tool)) return;
        vistos.add(h.tool);

        const d = document.createElement("div");
        d.className = "traza-item";
        d.innerHTML =
          '<div class="traza-tool">' + escapar(h.tool) + "</div>" +
          '<div class="traza-input">' + escapar(JSON.stringify(h.input || {})) + "</div>" +
          '<div class="traza-regla"><b>Regla:</b> ' + escapar(h.regla || "") + "</div>" +
          '<div class="traza-res">' + escapar(JSON.stringify(resumir(h.resultado))) + "</div>";
        body.appendChild(d);
      });
    });
  }

  function resumir(obj) {
    if (!obj || typeof obj !== "object") return obj;
    const out = {};
    Object.keys(obj).forEach((k) => {
      const v = obj[k];
      if (typeof v === "number") out[k] = Math.round(v * 100) / 100;
      else if (Array.isArray(v)) out[k] = "[" + v.length + " elementos]";
      else if (v && typeof v === "object") out[k] = "{…}";
      else out[k] = v;
    });
    return out;
  }

  // ---------------------------------------------------------------
  // Chat
  // ---------------------------------------------------------------
  async function enviarPregunta(pregunta) {
    const msgs = $("#chatMessages");
    const input = $("#chatInput");
    const btn = $(".btn-send");

    if (!pregunta.trim()) return;

    msgs.appendChild(divMsg("user", pregunta));
    input.value = "";
    btn.disabled = true;

    const typing = document.createElement("div");
    typing.className = "msg bot";
    typing.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    msgs.appendChild(typing);
    msgs.scrollTop = msgs.scrollHeight;

    try {
      const ctx = state.contexto || {};
      const r = CFG.modoDemo
        ? await preguntarDemo(pregunta, ctx)
        : await preguntar(pregunta, ctx);

      typing.remove();

      const texto = r.respuesta || "";
      const reglas = (r.herramientas || []).map((h) =>
        '<div class="regla"><b>' + escapar(h.tool) + ":</b> " + escapar(h.regla || "") + "</div>"
      ).join("");

      const d = divMsg("bot", "<p>" + md(texto) + "</p>" + reglas);
      msgs.appendChild(d);
      msgs.scrollTop = msgs.scrollHeight;

      // Actualiza la traza
      if (state.ultimoAnalisis) {
        state.ultimoAnalisis.push({ pregunta, ...r });
        pintarTraza(state.ultimoAnalisis);
      }
    } catch (err) {
      typing.remove();
      console.error(err);
      msgs.appendChild(divMsg("bot", "<p>No he podido procesarlo: " + escapar(err.message || err) + "</p>"));
    } finally {
      btn.disabled = false;
      input.focus();
    }
  }

  function divMsg(rol, html) {
    const d = document.createElement("div");
    d.className = "msg " + rol;
    d.innerHTML = html;
    return d;
  }

  // ---------------------------------------------------------------
  // Modal
  // ---------------------------------------------------------------
  function abrirModal(f) {
    const body = $("#modalBody");
    const movs = f.movimientos_involucrados || [];

    let html = '<h3 id="modalTitulo">' + escapar(f.descripcion.split(".")[0]) + "</h3>";

    if (f.importe_anual) {
      html += '<div class="big-amount">' + eur(f.importe_anual, 2) + "</div>";
      html += '<div class="modal-sub">al año · ' + eur((f.importe_anual / 12), 2) + " al mes</div>";
    }

    html += '<div class="modal-body-text"><p>' + escapar(f.descripcion) + "</p>";

    if (f.accion_sugerida) {
      html += '<p><strong>Qué hacer:</strong> ' + escapar(f.accion_sugerida) + "</p>";
    }

    if (movs.length) {
      html += "<p><strong>Movimientos implicados:</strong></p><ul>";
      movs.slice(0, 8).forEach((m) => {
        const imp = Number(m.importe);
        html += "<li>" + escapar(m.fecha) + " · " + escapar(m.concepto || "") +
          " · " + eur(Math.abs(imp), 2) + "</li>";
      });
      html += "</ul>";
    }

    html += "</div>";
    html += '<div class="regla-aplicada"><b>Cómo lo detectamos:</b> ' +
      escapar("Coincidencia de concepto e importe con frecuencia mensual, o concentración de gasto por categoría.") + "</div>";

    body.innerHTML = html;
    $("#modalBackdrop").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function cerrarModal() {
    $("#modalBackdrop").hidden = true;
    document.body.style.overflow = "";
  }

  // ---------------------------------------------------------------
  // Idioma
  // ---------------------------------------------------------------
  function aplicarIdioma() {
    $("#tituloContexto").textContent = t("tituloContexto");
    $("#subtituloContexto").textContent = t("subtituloContexto");
    $("#cardDatos").querySelector(".card-title").textContent = t("tusDatos");
    $("#cardDatos").querySelector(".card-hint").textContent = t("tusDatosHint");
    $("#btnAnalizar").querySelector("span").textContent = t("analizar");
    $("#trazaBox").querySelector("summary").textContent = t("razonamiento");
    $("#btnReiniciar").textContent = t("reiniciar");
    $$("#langSwitch span").forEach((s) => {
      s.classList.toggle("lang-active", s.textContent.toUpperCase() === lang.toUpperCase());
    });
    document.documentElement.lang = lang;
  }

  // ---------------------------------------------------------------
  // Arranque
  // ---------------------------------------------------------------
  function init() {
    inicializarOpciones();
    aplicarIdioma();

    $("#btnAnalizar").addEventListener("click", analizar);
    $("#btnReiniciar").addEventListener("click", () => {
      state.perfil = null;
      state.contexto = null;
      state.ultimoAnalisis = null;
      $("#chatMessages").innerHTML = "";
      $("#hallazgos").innerHTML = "";
      $$("#opcionesInicio .opcion").forEach((b) => b.classList.remove("selected"));
      $("#uploadZone").hidden = true;
      ["rentaNeta", "margenBruto", "saldoActual", "actividad"].forEach((id) => { $("#" + id).value = ""; });
      mostrarPaso(1);
    });

    $("#chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      enviarPregunta($("#chatInput").value);
    });

    $("#langSwitch").addEventListener("click", () => {
      const orden = ["es", "ca", "en"];
      lang = orden[(orden.indexOf(lang) + 1) % orden.length];
      aplicarIdioma();
    });

    $("#modalClose").addEventListener("click", cerrarModal);
    $("#modalBackdrop").addEventListener("click", (e) => {
      if (e.target === $("#modalBackdrop")) cerrarModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("#modalBackdrop").hidden) cerrarModal();
    });

    if (CFG.modoDemo) {
      console.info("[MoraBanc] Modo demo: datos precalculados por el motor real (Python).");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
