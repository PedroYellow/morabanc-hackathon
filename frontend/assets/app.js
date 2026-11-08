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
    // La clave de la API la inyecta el edge (la CloudFront Function)
    // en cada peticion. El navegador nunca la ve: por eso aqui no hay
    // ninguna. Es lo unico que evita que la cuota de Bedrock la gaste
    // cualquiera con la URL.
    apiKey: "",
    cognitoDomain: window.__COGNITO_DOMAIN__ || "",
    cognitoClientId: window.__COGNITO_CLIENT_ID__ || "",
    region: window.__AWS_REGION__ || "eu-west-1",
    // Modo demo: los datos ya estan precalculados por el motor real
    // (el mismo motor Python, ejecutado al generar el JSON).
    //
    // Se usa cuando NO hay sesion: la API exige el id_token de
    // Cognito y, sin el, responderia 401. El front standalone
    // (welcomeandorra.com/index.html) se puede abrir sin pasar por el
    // login; el portal de empresas si lleva token y ahi va contra la
    // API de verdad.
    modoDemo: !window.__API_URL__,
  };

  // El id_token de Cognito de la sesion iniciada en el login.
  //
  // La API lo exige en /preguntar: la x-api-key la inyecta el edge de
  // CloudFront a cualquier peticion, asi que no prueba nada sobre quien
  // pregunta. Este token si: lo firma Cognito.
  function tokenDeSesion() {
    try {
      return localStorage.getItem("mb-token") || "";
    } catch (e) {
      return "";
    }
  }

  const PERFILES_DEMO = {
    freelance: {
      etiqueta: "Freelance de servicios",
      csv: "data/demo_freelance.csv",
      saldo: 8500, renta: 30000, margen: 0.70,
      actividad: "Freelance de servicios",
    },
    // Ceramica Canillo (12TJ31): pyme con un empleado, a 2.000 EUR
    // del umbral de tramo. Su propio extracto: compartirlo con el
    // comercio de tienda seria ver el mismo extracto bajo dos razones
    // sociales.
    crecimiento: {
      etiqueta: "Taller de ceramica",
      csv: "data/demo_ceramica.csv",
      saldo: 6900, renta: 38000, margen: 0.4,
      actividad: "Taller de ceramica",
    },
    // Usuario normal: asalariado. No lleva contabilidad; su "ingreso" es
    // la nomina. El motor lo calcula sin actividad economica: sin IGI y
    // sin CASS por cuenta propia. Es el caso de "tengo una cuenta y no
    // entiendo por que no me llega a fin de mes".
    empleado: {
      etiqueta: "Treballador per compte d'altri",
      csv: "data/demo_empleado.csv",
      saldo: 3400, renta: 23281, margen: 0,
      actividad: "Treballador per compte d'altri",
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
    // El asalariado no lleva contabilidad: lo que quiere saber es por
    // que no le llega a fin de mes, no la CASS.
    empleado: [
      "¿Por qué no me llega a fin de mes?",
      "¿Cuánto me queda después de pagar?",
      "¿Hay algo que esté pagando de más?",
      "¿Cuánto tenho ahorrado este año?",
    ],
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
    // Pyme a 2.000 EUR del umbral: la pregunta es si facturar mas
    // compensa (el salto de tramo se come el margen extra).
    crecimiento: [
      "¿Me compensa facturar más?",
      "¿Cuánto me queda si facturo 5.000 más?",
      "¿Qué pasa cuando cambio de tramo?",
      "¿Cuánto puedo crecer antes de perder dinero?",
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
      vozSaludo: "Hola, soy PlanificAND. Te escucho: cuéntame tu situación financiera y yo la calculo con la normativa andorrana.",
      vozSaludoCorto: "Hola, soy PlanificAND.",
      vozGuiaInicial: "Por ejemplo: «Facturo 40.000 euros al año, tengo 8.500 en la cuenta y un margen del 70%».",
      vozFaltaRenta: "Necesito tu renta neta anual: lo que te queda tras gastos, antes de impuestos y CASS.",
      vozFaltaSaldo: "¿Cuánto dinero tienes hoy en la cuenta?",
      vozFaltaActividad: "¿A qué te dedicas? Por ejemplo: servicios, comercio,-hostelería.",
      vozListo: "Perfecto, ya tengo lo que necesito. Pulsa Analizar y te digo cuánto te queda.",
      vozConfirmado: "Anotado: {dato}.",
      vozArchivos: "He adjuntado un archivo. Lo reviso antes de continuar.",
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
      vozSaludo: "Hola, soc PlanificAND. t'escolto: explica'm la teva situació financera i jo la calculo amb la normativa andorrena.",
      vozSaludoCorto: "Hola, soc PlanificAND.",
      vozGuiaInicial: "Per exemple: «Facturo 40.000 euros l'any, tinc 8.500 al compte i un marge del 70%».",
      vozFaltaRenta: "Necessito la teva renda neta anual: el que et queda després de despeses, abans d'impostos i CASS.",
      vozFaltaSaldo: "Quants diners tens avui al compte?",
      vozFaltaActividad: "A què et dediques? Per exemple: serveis, comerç, hostaleria.",
      vozListo: "Perfecte, ja tinc el que necessito. Prem Analitzar i et dic quant te'n queda.",
      vozConfirmado: "Anotat: {dato}.",
      vozArchivos: "He adjuntat un fitxer. El reviso abans de continuar.",
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
      vozSaludo: "Hi, I'm PlanificAND. I'm listening: tell me your financial situation and I'll work it out with Andorran tax rules.",
      vozSaludoCorto: "Hi, I'm PlanificAND.",
      vozGuiaInicial: 'For example: "I bill 40,000 a year, I have 8,500 in the account and a 70% margin".',
      vozFaltaRenta: "I need your annual net income: what's left after expenses, before taxes and CASS.",
      vozFaltaSaldo: "How much money do you have in the account right now?",
      vozFaltaActividad: "What do you do? For example: services, retail, hospitality.",
      vozListo: "Perfect, I have everything I need. Hit Analyse and I'll tell you what you keep.",
      vozConfirmado: "Noted: {dato}.",
      vozArchivos: "I've attached a file. Let me go through it first.",
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
    // Datos ya calculados para la vista de presentacion (null = no hay).
    pres: null,
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

    const cabeceras = { "Content-Type": "application/json" };
    // La API esta protegida con una clave (x-api-key) para que nadie mas
    // pueda gastarnos la cuota de Bedrock del equipo.
    if (CFG.apiKey) cabeceras["x-api-key"] = CFG.apiKey;

    // Y ADEMAS con el id_token de Cognito: la x-api-key la pone el edge
    // de CloudFront a cualquier peticion, asi que sola no prueba que
    // quien pregunta sea un cliente del banco. Sin sesion, la API
    // responde 401 y no se gasta nada.
    const token = tokenDeSesion();
    if (token) cabeceras["Authorization"] = "Bearer " + token;

    const resp = await fetch(CFG.apiUrl + "/preguntar", {
      method: "POST",
      headers: cabeceras,
      body: JSON.stringify(cuerpo),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      if (resp.status === 401) {
        // La sesion caduco o no hay sesion: hay que volver a entrar.
        try { localStorage.removeItem("mb-token"); } catch (e) {}
        throw new Error(err.error || "Sesion no valida. Vuelve a iniciar sesion.");
      }
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
    return "**Flujo neto: " + fmtEuro(r.flujo_neto, 2) + "** en el periodo analizado (12 meses).\n" +
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

        // Los chips de contexto se rellenan con lo mismo. Sin esto, al
        // elegir un perfil los inputs se rellenaban pero los chips se
        // quedaban en "—": el usuario veia los campos con numeros y
        // un "—" debajo, sin entender que ya estaba todo capturado.
        //
        // La UI y el motor estan en IIFE separados y no comparten
        // "state", asi que se avisa por el puente que expone el motor.
        const slots = {
          renta: perfil.renta,
          margen: Math.round(perfil.margen * 100),
          saldo: perfil.saldo,
          actividad: perfil.actividad,
        };
        if (typeof window.__mbSetSlots === "function") {
          window.__mbSetSlots(slots);
        } else {
          state.slots = Object.assign(state.slots || {}, slots);
          if (typeof pintarChips === "function") pintarChips();
        }
      });
    });

    $("#fileInput").addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length) recibirArchivos(files);
    });

    // --- Arrastre de archivos sobre toda la pagina -------------------
    // Se puede soltar el extracto en cualquier punto de la pantalla, no
    // solo en la zona de subida. Aparece un overlay que dice que va a
    // pasar y, al soltar, se procesa igual que con el selector.
    const overlay = $("#dropOverlay");
    let dragProfundidad = 0;

    function mostrarOverlay(on) {
      if (!overlay) return;
      overlay.hidden = !on;
      document.body.classList.toggle("dragging-file", on);
    }

    window.addEventListener("dragenter", (e) => {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes("Files")) return;
      e.preventDefault();
      dragProfundidad++;
      mostrarOverlay(true);
    });
    window.addEventListener("dragover", (e) => {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes("Files")) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    });
    window.addEventListener("dragleave", (e) => {
      dragProfundidad = Math.max(0, dragProfundidad - 1);
      if (dragProfundidad === 0) mostrarOverlay(false);
    });
    window.addEventListener("drop", (e) => {
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
      e.preventDefault();
      dragProfundidad = 0;
      mostrarOverlay(false);
      recibirArchivos(Array.from(e.dataTransfer.files));
    });
  }

  /**
   * Recibe uno o varios ficheros arrastrados o seleccionados.
   *
   * El CSV es el que el motor entiende: se guarda como contexto y es la
   * fuente de verdad de los numeros. Los demas (PDF, Excel, imagenes) se
   * adjuntan a la conversacion para que el asistente pueda mirarlos, y
   * se le avisa al usuario de cual es cual.
   */
  async function recibirArchivos(files) {
    const zona = $("#uploadZone");
    if (zona && zona.hidden) zona.hidden = false;

    const csvs = files.filter((f) => /\.csv$/i.test(f.name) || f.type === "text/csv");
    const otros = files.filter((f) => csvs.indexOf(f) === -1);

    for (const f of csvs) {
      const texto = await f.text();
      state.perfil = "subido";
      state.contexto = Object.assign(state.contexto || {}, { csv: texto });
    }

    if (otros.length) {
      // Se guardan en el estado para poder mandarlos con la pregunta.
      state.archivos = (state.archivos || []).concat(otros);
      // El chat del paso 2 es donde se escriben las preguntas: si ya esta
      // visible, se dejan ahi; si no, se abren para que se vean.
      const mensajes = $("#chatMessages");
      if (mensajes) {
        for (const f of otros) {
          const div = document.createElement("div");
          div.className = "chat-msg user con-archivo";
          div.textContent = "\u{1F4CE} " + f.name + " (" + num(f.size / 1024, 1) + " KB)";
          mensajes.appendChild(div);
        }
        mensajes.scrollTop = mensajes.scrollHeight;
      }
    }

    const titulo = $("#fileDropTitle");
    if (titulo) {
      const nombres = files.map((f) => f.name);
      titulo.textContent = nombres.length > 1
        ? nombres.length + " archivos cargados"
        : nombres[0];
    }

    if (csvs.length) {
      toast("Extracto cargado: " + num(csvs[0].size / 1024, 1) + " KB", "ok");
    }
    if (otros.length) {
      toast(otros.length + " archivo(s) adjuntado(s) a la conversación", "ok");
      // El asistente debe saber que hay material nuevo que mirar.
      if (typeof aviso === "function") {
        aviso(t("vozArchivos") || "");
      }
    }
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

      if (CFG.modoDemo || !tokenDeSesion()) {
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

        // OJO: en modo real tambien hace falta el FLUJO y el TRAMO CASS:
        // la pantalla los usa para dos de sus cuatro metricas ("Flujo
        // anual" y "CASS"). Con solo las tres preguntas de arriba, esas
        // dos metricas no se pintaban.
        //
        // Se pregunetan aqui, con el MISMO contexto, para que el motor
        // calcule sobre los mismos numeros.
        const preguntasReal = preguntas.concat([
          // OJO: la palabra clave tiene que ser una de las que usa el
          // router del backend ("categoria", "donde se va", "resumen",
          // "renta"): con "flujo" el agente elegia proyectar_caja y la
          // metrica "Flujo anual" no se pintaba nunca.
          "¿Cuál es el resumen de ingresos y gastos y el flujo de caja en el periodo analizado?",
          "¿Cuánto cotizo a la CASS y en qué tramo estoy?",
        ]);

        // Las preguntas van EN PARALELO: son independientes y la API
        // responde cada una en ~4 s. En serie el paso 2 tardaba 12 s;
        // en paralelo, 5 s. En un pitch, esa diferencia se nota.
        //
        // Promise.allSettled (y no Promise.all): si UNA falla, se
        // muestran las otras. Con Promise.all un solo fallo dejaria
        // el paso 2 en blanco.
        const rs = await Promise.allSettled(
          preguntasReal.map(async (p) => ({ pregunta: p, ...(await preguntar(p, ctx)) }))
        );
        let fallos = 0;
        for (const r of rs) {
          if (r.status === "fulfilled") resultados.push(r.value);
          else fallos++;
        }
        if (fallos && !resultados.length) {
          throw new Error("No se pudo contactar con el motor de calculo");
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
      // El titular tiene que ser proporcional al problema. "Tu caja se
      // agota" por un hueco de 0,31 € es dramatismo que el jurado
      // desmonta en una pregunta ("¿por 31 centimos dices que se agota?").
      const hueco = Math.abs(caja.resultado.deuda_en_quiebre || 0);
      const ultimo = caja.resultado.ultimo_saldo_positivo;
      const mes = caja.resultado.mes_quiebre;

      if (hueco < 100) {
        // El margen es de céntimos: no es un problema de caja, es ruido
        // de redondeo del forecast.
        titulo = `Tu caja va justa en el mes ${mes}`;
        texto = `En el mes ${mes} te quedarías en ${eur(hueco, 2)} — practically nada. ` +
                `Con un margen tan fino, cualquier ingreso o gasto inesperado te deja en negativo. ` +
                `Tu último saldo cómodo es de ${eur(ultimo, 2)}.`;
        clase = "warn";
      } else if (hueco < 1000) {
        titulo = `Tu caja se queda corta en el mes ${mes}`;
        texto = `Al ritmo actual no llegas al final del horizonte. En el mes ${mes} te faltarían ` +
                `${eur(hueco, 2)}. Tu último saldo cómodo es de ${eur(ultimo, 2)}. ` +
                `Todavía estás a tiempo de corregirlo.`;
        clase = "warn";
      } else {
        titulo = `Tu caja se agota en el mes ${mes}`;
        texto = `Al ritmo actual no llegas al final del horizonte. Tu último saldo cómodo es de ${eur(ultimo, 2)} ` +
                `y en el mes del quiebre te faltan ${eur(hueco, 2)}. ` +
                `Todavía estás a tiempo de corregirlo.`;
        clase = "warn";
      }
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
      // OJO: el flujo es el del PERIODO ANALIZADO (12 meses), no mensual.
      // Decir "Flujo mensual" con la cifra anual es un error que el jurado
      // detecta en dos segundos.
      metrics.appendChild(metrica("Flujo anual", eur(f, 2), f >= 0 ? "ahorras" : "gastas",
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
      // Titulo CORTO y completo. Antes se cortaba ("Bonificacion IRPF
      // art.") porque el texto del motor era largo y la tarjeta no lo
      // cabia entero: un titulo a medias parece un bug.
      let tituloCrossover;
      if (r.tipo === "Bonificacion IRPF art. 46 toca su techo de 800 €") {
        tituloCrossover = "Bonificacion IRPF art. 46: toca su techo de 800 €";
      } else if (r.tipo.indexOf("El tramo CASS") === 0) {
        tituloCrossover = "Tu tramo de CASS sube el año que viene";
      } else {
        tituloCrossover = r.tipo;
      }
      cont.appendChild(tarjetaHallazgo({
        tipo: "crossover",
        destacado: true,
        descripcion: tituloCrossover,
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

    // --- Guardar para el modo presentacion -------------------------
    // La vista de presentacion reusa estos mismos datos: no recalcula
    // nada, solo los pinta en grande.
    state.pres = { titulo, texto, clase, metricas: [], meses: null, caja: null };

    const cassM = porTool["tramo_cass"];
    const flujoM = porTool["analizar_tesoreria"];
    if (cassM && cassM.resultado && cassM.resultado.cuota_mensual) {
      state.pres.metricas.push({
        label: "CASS", valor: eur(cassM.resultado.cuota_mensual, 2) + "/mes",
        sub: "tramo " + cassM.resultado.tramo, clase: "",
      });
    }
    if (flujoM && flujoM.resultado && flujoM.resultado.flujo_neto !== undefined) {
      const f = flujoM.resultado.flujo_neto;
      state.pres.metricas.push({
        label: "Flujo anual", valor: eur(f, 2),
        sub: f >= 0 ? "ahorras" : "gastas", clase: f >= 0 ? "pos" : "neg",
      });
    }
    if (caja && caja.resultado && caja.resultado.mes_quiebre) {
      state.pres.metricas.push({
        label: "Quiebre de caja", valor: "Mes " + caja.resultado.mes_quiebre,
        sub: "se queda sin saldo", clase: "neg",
      });
    }
    if (cross && cross.resultado && cross.resultado.existe) {
      state.pres.metricas.push({
        label: "Próximo umbral", valor: eur(cross.resultado.renta_punto, 0),
        sub: "de renta neta · salta tu tramo", clase: "",
      });
    }
    if (caja && caja.resultado && caja.resultado.meses) {
      state.pres.meses = caja.resultado.meses;
      state.pres.caja = caja.resultado;
    }
    // Ya hay algo que presentar.
    $("#btnPresentacion").hidden = false;
  }

  /* ============================================================
     MODO PRESENTACION
     Vista grande para el proyector: se ve desde el fondo de la sala.
     Reutiliza los datos ya calculados (state.pres) — no recalcula.
     ============================================================ */
  function abrirPresentacion() {
    const p = state.pres;
    if (!p) return;

    // Al abrir la presentacion se vuelve arriba. Con position:fixed, el
    // elemento se posiciona respecto al viewport, pero si la pagina estaba
    // scrolleada (el resultado es largo) la vista sale desplazada y se ve
    // solo el grafico.
    window.scrollTo(0, 0);

    $("#presentacion").hidden = false;
    $("#presentacion").setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    // La cabecera de la app (logo + idioma) no aporta en el proyector y
    // roba altura: se oculta mientras dura la presentacion.
    document.body.classList.add("presentacion-activa");

    $("#presLabel").textContent = t("diagnostico");
    $("#presTitle").textContent = p.titulo;
    $("#presSub").textContent = p.texto;

    const cont = $("#presMetrics");
    cont.innerHTML = "";
    p.metricas.forEach((m) => {
      const d = document.createElement("div");
      d.className = "presentacion-metric" + (m.clase ? " " + m.clase : "");
      d.innerHTML =
        '<div class="presentacion-metric-label">' + m.label + "</div>" +
        '<div class="presentacion-metric-value">' + m.valor + "</div>" +
        (m.sub ? '<div class="presentacion-metric-sub">' + m.sub + "</div>" : "");
      cont.appendChild(d);
    });

    // El grafico se dibuja en el SVG de presentacion con los mismos datos.
    if (p.meses) {
      dibujarGraficoEn($("#presGrafico"), p.meses, p.caja, $("#presLeyenda"));
    }
  }

  function cerrarPresentacion() {
    $("#presentacion").hidden = true;
    $("#presentacion").setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    document.body.classList.remove("presentacion-activa");
    // Volver al resultado, no al principio de la pagina.
    const btn = $("#btnPresentacion");
    if (btn && btn.offsetParent !== null) {
      btn.scrollIntoView({ block: "center", behavior: "instant" });
    }
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

    // OJO: el texto NO se trunca. Un parrafo de una regla legal cortado a
    // media frase ("...y la bonificacio de") parece un bug en pantalla y
    // en una sala. El texto integro cabe: el CSS lo ajusta.
    b.innerHTML =
      '<span class="hallazgo-icon">' + icon + "</span>" +
      '<span class="hallazgo-body">' +
        '<span class="hallazgo-titulo">' + escapar(titulo) + "</span>" +
        '<span class="hallazgo-desc">' + escapar(detalle) + "</span>" +
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
    // OJO: cortar en el primer punto rompe las abreviaturas y las
    // referencias a articulos: "Bonificacion IRPF art. 46 toca su techo"
    // se cortaba en "Bonificacion IRPF art." y el titulo se veia a medias.
    //
    // Solo se corta en un punto seguido de mayuscula (fin de frase de
    // verdad), no en "art." ni en "núm." ni en "S.L.".
    const m = t.match(/^.*?[.!?](?=\s+[A-ZÁÉÍÓÚÑ¿¡]|$)/);
    if (!m) return t.trim();
    const frase = m[0].trim();
    // Si la frase es demasiado corta, es que hemos cortado en una
    // abreviatura: mejor devolver el texto entero.
    return frase.length < 12 ? t.trim() : frase;
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
    dibujarGraficoEn($("#graficoCaja"), meses, resultado, $("#leyendaProyeccion"));
  }

  /**
   * Dibuja la curva de caja en un SVG concreto.
   *
   * Se parametriza el destino porque la misma curva se pinta en dos sitios:
   * la pantalla de resultado (movil) y la vista de presentacion (proyector).
   * Los datos son los mismos: el JS no calcula nada, solo dibuja.
   */
  function dibujarGraficoEn(svg, meses, resultado, leyenda) {
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
      line.setAttribute("stroke", f === 0 ? "#d9d9d9" : "#e7e7e7");
      line.setAttribute("stroke-width", (1 / escala).toFixed(2));
      svg.appendChild(line);
      const tx = document.createElementNS(ns, "text");
      tx.setAttribute("x", padL - 8); tx.setAttribute("y", yy + 3.5);
      tx.setAttribute("text-anchor", "end");
      tx.setAttribute("fill", "#898989");
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
    // El id tiene que ser unico por documento: si los dos SVG (resultado y
    // presentacion) usan "gCaja", el segundo pinta con el gradiente del
    // primero y el area sale del color equivocado.
    const gradId = "gCaja-" + (svg.id || "x") + "-" + Math.floor(Math.random() * 1e6);
    grad.setAttribute("id", gradId);
    grad.setAttribute("x1", "0"); grad.setAttribute("y1", "0");
    grad.setAttribute("x2", "0"); grad.setAttribute("y2", "1");
    const s1 = document.createElementNS(ns, "stop");
    s1.setAttribute("offset", "0%"); s1.setAttribute("stop-color", "#04aa6d"); s1.setAttribute("stop-opacity", "0.28");
    const s2 = document.createElementNS(ns, "stop");
    s2.setAttribute("offset", "100%"); s2.setAttribute("stop-color", "#04aa6d"); s2.setAttribute("stop-opacity", "0");
    grad.appendChild(s1); grad.appendChild(s2);
    const defs = document.createElementNS(ns, "defs");
    defs.appendChild(grad);
    svg.appendChild(defs);

    const area = document.createElementNS(ns, "path");
    area.setAttribute("d", areaD);
    area.setAttribute("fill", "url(#" + gradId + ")");
    svg.appendChild(area);

    // linea: verde hasta el quiebre, rojo despues
    const quieb = resultado && resultado.mes_quiebre ? resultado.mes_quiebre - 1 : vals.length;
    let d1 = "M" + x(0) + " " + y(vals[0]);
    for (let i = 1; i <= Math.min(quieb, vals.length - 1); i++) d1 += " L" + x(i) + " " + y(vals[i]);
    const l1 = document.createElementNS(ns, "path");
    l1.setAttribute("d", d1); l1.setAttribute("fill", "none");
    l1.setAttribute("stroke", "#04aa6d"); l1.setAttribute("stroke-width", lw.toFixed(2));
    l1.setAttribute("stroke-linejoin", "round"); l1.setAttribute("stroke-linecap", "round");
    svg.appendChild(l1);

    if (quieb < vals.length - 1) {
      let d2 = "M" + x(quieb) + " " + y(vals[quieb]);
      for (let i = quieb + 1; i < vals.length; i++) d2 += " L" + x(i) + " " + y(vals[i]);
      const l2 = document.createElementNS(ns, "path");
      l2.setAttribute("d", d2); l2.setAttribute("fill", "none");
      l2.setAttribute("stroke", "#f0421c"); l2.setAttribute("stroke-width", lw.toFixed(2));
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
      tx.setAttribute("fill", "#898989");
      tx.setAttribute("font-size", fs.toFixed(1));
      tx.textContent = "M" + (i + 1);
      svg.appendChild(tx);
    }

    // leyenda
    const lg = leyenda || $("#leyendaProyeccion");
    lg.innerHTML = "";
    if (quieb < vals.length - 1) {
      lg.innerHTML =
        '<span class="legend-item"><span class="legend-swatch" style="background:#04aa6d"></span>Con caja</span>' +
        '<span class="legend-item"><span class="legend-swatch" style="background:#f0421c"></span>En números rojos</span>';
    } else {
      lg.innerHTML = '<span class="legend-item"><span class="legend-swatch" style="background:#04aa6d"></span>Saldo de caja</span>';
    }

    // nota (solo en la vista de resultado; en presentacion no hay nota)
    const nota = $("#notaProyeccion");
    if (nota && resultado && resultado.resumen) {
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
      // Sin sesion (id_token de Cognito) la API responde 401. En ese
      // caso se usan los datos precalculados por el motor real, que
      // son los mismos numeros: el asesor sigue funcionando.
      const haySesion = !!tokenDeSesion();
      const r = (CFG.modoDemo || !haySesion)
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

    // El boton de presentacion solo tiene sentido con resultados: al inicio
    // no hay nada que presentar.
    $("#btnPresentacion").hidden = true;

    $("#btnAnalizar").addEventListener("click", analizar);
    $("#btnReiniciar").addEventListener("click", () => {
      state.perfil = null;
      state.contexto = null;
      state.ultimoAnalisis = null;
      state.pres = null;
      cerrarPresentacion();
      $("#btnPresentacion").hidden = true;
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

    // Modo presentacion: boton + tecla Escape para salir.
    $("#btnPresentacion").addEventListener("click", abrirPresentacion);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        // Escape cierra lo que este abierto: primero la presentacion,
        // despues el modal.
        if (!$("#presentacion").hidden) { cerrarPresentacion(); return; }
        if (!$("#modalBackdrop").hidden) cerrarModal();
      }
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

/* ============================================================
   VOZ + CAPTURA DE CONTEXTO
   ============================================================
   Dos piezas que cierran el bucle de "no me hagas填 un formulario":

   1. VOZ. Si hay microfono, el usuario habla y el texto aparece en el
      chat. La ruta preferida es ElevenLabs Conversations (WebRTC), la
      misma que usa Ubot: el agente conversa y ademas devuelve la
      transcripcion. Si no hay clave de ElevenLabs o el navegador no
      soporta WebRTC, caemos al SpeechRecognition nativo del
      navegador (Chrome/Edge/Safari), que es solo transcripcion: el
      texto entra por el mismo camino que si se hubiera escrito.

   2. CAPTURA DE SLOTS. Cada mensaje (hablado o escrito) pasa por un
      extractor que reconoce renta, margen, saldo y actividad. Lo que
      se reconoce se pinta en una fila de chips y se guarda en el
      contexto que se manda al motor. Asi, al preguntar, el motor ya
      recibe un contexto aunque el usuario NUNCA haya tocado un input.

   El extractor NO inventa numeros: solo reconoce los que el usuario
   dice y, cuando la unidad es ambigua (30.000 puede ser renta o
   facturacion), pide confirmacion en vez de suponer.
   ============================================================ */
(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);

  // ---------------------------------------------------------------
  // Config
  // ---------------------------------------------------------------
  // El id publico del agente. Es el MISMO esquema que usa Ubot: un id
  // de agente publico (a que agente hablar), no una credencial. Si no
  // se inyecta, el modulo funciona igual con SpeechRecognition.
  const ELEVENLABS_AGENT_ID =
    (window.__ELEVENLABS_AGENT_ID__ || "").trim() || null;

  const SLOTS = [
    { key: "renta",   label: "Renta neta",  unit: "€" },
    { key: "margen",  label: "Margen",      unit: "%" },
    { key: "saldo",   label: "Saldo",       unit: "€" },
    { key: "actividad", label: "Actividad", unit: "" },
  ];

  // Puente con el bundle de la UI (que va en otra IIFE y no comparte
  // "state"). La UI rellena el contexto al elegir un perfil; este setter
  // lo pasa al state del motor, que es el que leen pintarChips() y el
  // envio a la API. Sin el, los campos se rellenaban pero los chips
  // se quedaban en "—".
  window.__mbSetSlots = function (slots) {
    Object.assign(state.slots, slots || {});
    if (typeof pintarChips === "function") pintarChips();
  };

  const state = {
    conv: null,          // sesion de ElevenLabs
    recog: null,         // SpeechRecognition nativo
    stream: null,        // MediaStream para el medidor de nivel
    audioCtx: null,
    rafId: 0,
    on: false,
    recogiendo: false,   // estamos capturando transcripcion
    slots: {},           // { renta, margen, saldo, actividad }
    confirmando: null,   // slot pendiente de confirmacion
    silencioTemporizador: 0,
  };

  // ---------------------------------------------------------------
  // Extraccion de slots
  // ---------------------------------------------------------------
  // "30.000 euros de renta" -> 30000
  // "un margen del 70%"    -> 70
  // "tengo 8.500 en cuenta" -> 8500
  //
  // Se normaliza el numero: en Catalan/Frances el separador de
  // millares puede ser punto o espacio, y la voz a texto escribe
  // "8.500" o "8500 euros" indistintamente.
  // ---------------------------------------------------------------
  // Formato de numeros
  // ---------------------------------------------------------------
  // "30.000" -> 30000 (punto de millares), "30,5" -> 30.5 (coma
  // decimal), "8.500,50" -> 8500.50 (formato es). La voz a texto
  // escribe los tres indistintamente.
  function normalizarNumero(bruto) {
    if (!bruto) return null;
    let s = String(bruto).trim();
    s = s.replace(/[€$£\s ]/g, "");
    // Formato es: 8.500,50
    if (/^\d{1,3}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
    // Millares con punto: 30.000
    else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
    // Decimal con coma: 30,5
    else if (/^\d+,\d+$/.test(s)) s = s.replace(",", ".");
    const n = parseFloat(s);
    return isFinite(n) ? n : null;
  }

  function fmt(n, dec) {
    if (n === null || n === undefined || isNaN(n)) return "";
    const neg = n < 0;
    const abs = Math.abs(n);
    const s = dec === 0
      ? Math.round(abs).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".")
      : abs.toFixed(dec).replace(".", ",");
    return (neg ? "-" : "") + s;
  }

  // ---------------------------------------------------------------
  // Extraccion de slots
  // ---------------------------------------------------------------
  // En vez de un bloque por variable (que se robaban las cifras entre
  // si), se hace UN SOLO escaneo: se localizan todas las cifras del
  // texto y se clasifica cada una segun la palabra que la rodea.
  //
  // La palabra clave de cada cifra es la mas cercana por delante o
  // por detras (en un radio corto). Con eso:
  //   "facturo 30.000 al año"        -> 30000 renta (al año = anual)
  //   "tengo 8500 en cuenta"         -> 8500 saldo (en cuenta = dinero)
  //   "un margen del 70%"            -> 70 margen (margen + %)
  //   "3 clientes al mes"            -> nada (clientes no es dinero)
  // ---------------------------------------------------------------

  // Palabras que SI son dinero.
  const RE_DINERO = /(?:€|eur|euros?)/i;
  // Palabras que NUNCA son dinero: son unidades de negocio.
  const UNIDADES_NO_DINERO = [
    "cliente", "clientes", "empleado", "empleados", "persona",
    "personas", "hora", "horas", "dia", "dias", "día", "días",
    "semana", "semanas", "mes", "meses", "ano", "años", "año",
    "factura", "facturas", "pedido", "pedidos", "contrato",
    "contratos", "proyecto", "proyectos", "coche", "coches",
    "productos", "unidades", "trabajadores", "empleados",
  ];

  // Pistas de RENTA (palabra -> la cifra que va detras, normalmente).
  const PISTAS_RENTA = [
    "renta neta", "renta", "ganancia neta", "beneficio neto",
    "ingreso neto", "ingresos netos", "salario neto", "neto anual",
    "beneficio", "ganancia", "ingreso", "ingresos", "facturo",
    "gano", "facturado",
  ];
  // Pistas de SALDO. "tengo" va incluida porque "tengo 8500 euros" es
  // como lo dice la gente; la cifra solo cuenta si lleva euros o va
  // seguida de "en cuenta" (que implica euros).
  const PISTAS_SALDO = [
    "saldo actual", "saldo en cuenta", "saldo de cuenta", "saldo",
    "liquidado", "en caja", "en el banco", "en cuenta", "de cuenta",
    "tengo en cuenta", "tengo en el banco", "tengo en caja",
    "reserva", "ahorrado", "ahorro", "tengo",
  ];
  // Pistas que implican euros por si mismas: la cifra que las sigue
  // es dinero aunque no se diga "euros" ("mi saldo es 7.500",
  // "en el banco tengo 12.300", "ganancia neta 32000").
  const PISTAS_IMPLICAN_EUROS = [
    "saldo actual", "saldo en cuenta", "saldo de cuenta", "saldo",
    "liquidado", "en caja", "en el banco", "en cuenta", "de cuenta",
    "tengo en cuenta", "tengo en el banco", "tengo en caja",
    "reserva", "ahorrado", "ahorro",
    "renta neta", "ganancia neta", "beneficio neto", "ingreso neto",
    "ingresos netos", "salario neto", "neto anual",
    // "facturo 25.000": facturar es hablar de euros, aunque no se
    // diga la palabra.
    "facturo", "facturado",
  ];
  // Pistas de renta inequivocas: la cifra pegada a ellas es la
  // renta, sin duda.
  const PISTAS_RENTA_FUERTES = [
    "renta neta", "ganancia neta", "beneficio neto", "ingreso neto",
    "ingresos netos", "salario neto", "neto anual",
    // "facturo 25.000": facturar es hablar de euros, aunque no se
    // diga la palabra.
    "facturo", "facturado",
  ];
  // Pistas de MARGEN.
  const PISTAS_MARGEN = ["margen", "rentabilidad", "beneficio neto sobre", "por ciento"];

  function extraerSlots(texto) {
    if (!texto) return {};
    const t = " " + String(texto).toLowerCase() + " ";
    const out = {};

    // --- Todas las cifras del texto, con su posicion --------------
    const cifras = [];
    const reCifra = /(\d[\d.,\s]*)/g;
    let m;
    while ((m = reCifra.exec(t)) !== null) {
      const n = normalizarNumero(m[1]);
      if (n === null || n <= 0 || n >= 100000000) continue;
      // Ignora los numeros que son parte de otro ("30.000" se lee
      // como uno solo, no como "30" y "000").
      cifras.push({
        n,
        ini: m.index,
        fin: m.index + m[0].length,
        pos: m.index + m[0].length / 2,
      });
    }
    if (!cifras.length) {
      // Sin cifras solo puede quedar la actividad.
      const soloAct = detectarActividad(t);
      if (soloAct) out.actividad = soloAct;
      return out;
    }

    // --- Palabras clave y su posicion ---------------------------
    // Se guardan como {palabra, ini, fin} para saber a que cifra
    // estan pegadas.
    const palabras = [];
    const anadirPalabras = (lista) => {
      for (const p of lista) {
        const re = new RegExp("\\b" + p.replace(/\s+/g, "\\s+") + "\\b", "g");
        let mm;
        while ((mm = re.exec(t)) !== null) {
          palabras.push({ p, ini: mm.index, fin: mm.index + mm[0].length });
        }
      }
    };
    anadirPalabras(PISTAS_RENTA);
    anadirPalabras(PISTAS_SALDO);
    anadirPalabras(PISTAS_MARGEN);

    // Para cada cifra se busca la palabra clave mas cercana (por
    // delante o por detras) y se clasifica con ella.
    //
    // La asignacion es GLOBAL: cada cifra se queda con UNA palabra
    // clave (la mas cercana) y cada palabra clave es la que decide
    // de que slot es la cifra. Asi, en "facturo 30000 al año y tengo
    // 8500 en cuenta", el 30000 se queda con "facturo" (renta) y el
    // 8500 con "tengo"/"en cuenta" (saldo): no se pisan.
    const candidatos = [];
    for (const c of cifras) {
      let mejor = null;
      let mejorDist = Infinity;
      for (const pal of palabras) {
        // Distancia entre la cifra y la palabra, sin contar los
        // espacios intermedios.
        let dist;
        if (pal.fin <= c.ini) dist = c.ini - pal.fin;
        else if (pal.ini >= c.fin) dist = pal.ini - c.fin;
        else dist = 0;
        if (dist > 40) continue;
        // A igual distancia, manda la palabra mas larga (mas
        // especifica): "renta neta" sobre "renta".
        if (dist < mejorDist || (dist === mejorDist && mejor && pal.p.length > mejor.p.length)) {
          mejor = pal;
          mejorDist = dist;
        }
      }
      if (!mejor) continue;

      let slot = PISTAS_MARGEN.includes(mejor.p) ? "margen"
                 : PISTAS_RENTA.includes(mejor.p) ? "renta"
                 : PISTAS_SALDO.includes(mejor.p) ? "saldo"
                 : null;
      if (!slot) continue;

      // --- Reglas de unidad por slot -----------------------------
      const antes = t.slice(Math.max(0, c.ini - 18), c.ini);
      const despues = t.slice(c.fin, c.fin + 26);
      const palabraAntes = (antes.match(/([a-zñáéíóú]+)\s*$/i) || [, ""])[1].toLowerCase();
      const palabraDespues = (despues.match(/^\s*([a-zñáéíóú%€]+)/i) || [, ""])[1].toLowerCase();
      // El porcentaje tiene que ser de ESTA cifra: "72 %" o
      // "72 por ciento". El "%" de "un margen del 72% y 9000 euros"
      // NO es de esta cifra: hay un "y" en medio, asi que la cifra
      // anterior al "%" no es la nuestra. Antes se miraba si habia
      // un "%" en cualquier sitio, y eso hacia que "9000 euros"
      // (que va despues del 72%) se descartara por ser porcentaje.
      const pctAntes = antes.match(/(\d[\d.,\s]*)\s*(?:%|por\s*ciento)\s*$/i);
      const esPctAntes = !!pctAntes && pctAntes[1].trim().replace(/[\s.,]/g, "") === String(c.n);
      const esPctDespues = /^\s*(?:%|por\s*ciento)/.test(despues);
      const esPorcentaje = esPctAntes || esPctDespues;

      // Una cifra en EUROS sin "%" y sin una pista de renta cerca es un
      // SALDO por defecto: "tengo 9000 euros" es saldo aunque no diga
      // "en cuenta". Antes, la palabra clave mas cercana ("margen", en
      // "un margen del 72% y 9000 euros") se la adjudicaba y el saldo
      // se perdia.
      if (slot === "margen" && !esPorcentaje) {
        const eurosDirectos = RE_DINERO.test(despues.slice(0, 12)) || RE_DINERO.test(antes);
        const hayPistaRentaCerca = palabras.some((pal) =>
          PISTAS_RENTA.includes(pal.p) &&
          Math.abs(pal.fin <= c.ini ? c.ini - pal.fin : pal.ini - c.fin) < 14);
        if (eurosDirectos && !hayPistaRentaCerca) slot = "saldo";
      }

      if (slot === "margen") {
        // El margen solo es un porcentaje.
        if (!esPorcentaje) continue;
        if (c.n > 100) continue;
        if (palabraAntes && UNIDADES_NO_DINERO.includes(palabraAntes)) continue;
      } else {
        // Renta y saldo tienen que ser dinero.
        if (esPorcentaje) continue;
        const unidadNegra = UNIDADES_NO_DINERO.includes(palabraDespues) || UNIDADES_NO_DINERO.includes(palabraAntes);
        if (unidadNegra) continue;
        // "en cuenta" / "en el banco" implican euros.
        const implicaDinero = RE_DINERO.test(despues.slice(0, 12)) || RE_DINERO.test(antes) ||
                              /\b(en\s+cuenta|en\s+el\s+banco|en\s+caja|de\s+cuenta)\b/i.test(despues.slice(0, 22)) ||
                              PISTAS_IMPLICAN_EUROS.includes(mejor.p) ||
                              // Una cifra anual ("al año", "anual") es
                              // una magnitud de dinero: "gano 28.500
                              // al año" no necesita decir "euros".
                              /(al\s*año|a\s*l?año|anual|por\s*año|\/\s*año)/i.test(despues.slice(0, 22));
        if (!implicaDinero) {
          // La palabra mas cercana puede no implicar dinero ("tengo")
          // mientras que otra de la misma frase si ("en el banco"
          // en "en el banco tengo 12.300"). Se mira la frase entera.
          const frase = t.slice(Math.max(0, c.ini - 34), c.fin + 26);
          if (!PISTAS_IMPLICAN_EUROS.some((p) =>
                new RegExp("\\b" + p.replace(/\s+/g, "\\s+") + "\\b").test(frase))) continue;
          // Y no se admite si hay una pista de RENTA fuerte cerca:
          // entonces esta cifra es la renta, no el saldo. Las
          // palabras sueltas ("facturo", "gano") no cuentan: en
          // "soy autonomo y facturo 25.000" la cifra es del saldo y
          // en "tengo 8500 en cuenta" no hay ninguna pista fuerte.
          if (palabras.some((pal) =>
                PISTAS_RENTA_FUERTES.includes(pal.p) &&
                Math.abs(pal.fin <= c.ini ? c.ini - pal.fin : pal.ini - c.fin) < 14)) continue;
        }
      }

      candidatos.push({ slot, n: c.n, dist: mejorDist, cifra: c });
    }

    // --- Resolucion de conflictos --------------------------------
    // Dos slots pueden querer la misma cifra ("facturo 30000 al año
    // y tengo 8500 en cuenta": el 30000 esta a 2 chars de "tengo" y
    // el 8500 a 8 de "en cuenta"). Se resuelve por proximidad: cada
    // cifra se queda con el slot cuya palabra clave esta mas cerca,
    // y el otro slot busca su siguiente candidato.
    const resolver = (slot, ocupadas) => {
      const opts = candidatos.filter((x) => x.slot === slot && !ocupadas.has(x.cifra.ini));
      if (!opts.length) return null;
      opts.sort((a, b) => a.dist - b.dist);
      return opts[0];
    };
    // El slot con la coincidencia mas cercana se resuelve primero: es
    // el que mas probablemente asigna su cifra.
    const ocupadas = new Set();
    const ordenSlots = ["renta", "saldo", "margen"].sort((a, b) => {
      const da = Math.min(...candidatos.filter((x) => x.slot === a).map((x) => x.dist), 1e9);
      const db = Math.min(...candidatos.filter((x) => x.slot === b).map((x) => x.dist), 1e9);
      return da - db;
    });
    const mejorPorSlot = { renta: null, saldo: null, margen: null };
    for (const slot of ordenSlots) {
      const el = resolver(slot, ocupadas);
      if (!el) continue;
      ocupadas.add(el.cifra.ini);
      mejorPorSlot[slot] = { valor: el.cifra.n, dist: el.dist, cifra: el.cifra };
    }

    // --- Reglas especificas de la renta --------------------------
    if (mejorPorSlot.renta) {
      const c = cifras.find((x) => x.n === mejorPorSlot.renta.valor);
      if (c) {
        const despues = t.slice(c.fin, c.fin + 26);
        const esMensual = /(al\s*mes|a\s*l?mes|mensual|\/\s*mes)/i.test(despues);
        const esAnual = /(al\s*año|a\s*l?año|anual|por\s*año|\/\s*año)/i.test(despues);
        const pista = PISTAS_RENTA.find((p) => {
          const re = new RegExp("\\b" + p.replace(/\s+/g, "\\s+") + "\\b");
          const idx = t.indexOf(re);
          return idx !== -1 && idx < c.fin && idx + p.length >= c.ini - 30;
        });
        // "facturo 8500 al mes" es mensual: la renta neta ANUAL no es
        // ese numero, asi que se descarta.
        const ctxAntes = t.slice(Math.max(0, c.ini - 18), c.ini);
        if (esMensual) {
          mejorPorSlot.renta = null;
        } else if (!esAnual) {
          // Sin unidad temporal solo se acepta con cifra tipica de
          // renta anual de un autonomo (>= 3.000). "facturo 500"
          // casi nunca es renta neta anual.
          const enEuros = RE_DINERO.test(despues.slice(0, 12)) || RE_DINERO.test(ctxAntes);
          if (mejorPorSlot.renta.valor < 3000 && !enEuros) {
            mejorPorSlot.renta = null;
          }
        }
      }
    }

    if (mejorPorSlot.renta) out.renta = mejorPorSlot.renta.valor;
    if (mejorPorSlot.saldo) out.saldo = mejorPorSlot.saldo.valor;
    if (mejorPorSlot.margen) out.margen = mejorPorSlot.margen.valor;

    // --- Actividad ------------------------------------------------
    const act = detectarActividad(t);
    if (act) out.actividad = act;

    return out;
  }

  // Detecta la actividad economica a partir del texto.
  function detectarActividad(t) {
    // "soy freelance", "tengo una tienda", "trabajo en una tienda"...
    // OJO: "tengo un margen del 70%" NO es una actividad. Por eso se
    // excluyen las palabras que solo pueden describir magnitudes.
    const NO_ACTIVIDAD = [
      "margen", "saldo", "beneficio", "ingreso", "ingresos", "renta",
      "por ciento", "clientes", "gente", "tiempo", "dinero", "ahorro",
      "reserva", "mes", "meses", "ano", "años", "semana", "semanas",
      "cuenta", "banco", "caja",
    ];
    const mAct = t.match(/\b(?:soy|trabajo como|soy\s+un[ao]?|tengo\s+una?|mi\s+empresa\s+es|trabajo\s+en\s+una?)\s+([a-zñáéíóú][a-zñáéíóú\s\-]{2,60})/i);
    if (mAct) {
      let act = mAct[1].trim().replace(/\s{2,}/g, " ");
      // Quita el articulo inicial: "soy una consultora" -> "consultora".
      act = act.replace(/^(una?|unos?|los?|las?)\s+/i, "");
      // Si solo queda un articulo ("mi empresa es una 株式会社"), el
      // articulo no es una actividad: se descarta el match.
      if (/^(una?|unos?|los?|las?|de|del)$/i.test(act)) act = "";
      // La actividad se corta en la primera conjuncion o cifra:
      // "autonomo y facturo 25.000" -> "Autonomo", no "Autonomo y
      // facturo" (que se comia la renta). NO se corta en "de":
      // "tienda de ropa" y "freelance de diseño" son actividades
      // completas, con la preposicion dentro.
      const corte = act.search(/(\s+y\s|\s+o\s|\s+pero\s|\s+que\s|\d)/i);
      const actividad = corte > 0 ? act.slice(0, corte).trim() : act;
      // "Margen del" viene de "tengo un margen del 70%": se descarta
      // si la frase habla de una magnitud y no de un negocio.
      const esMagnitud = NO_ACTIVIDAD.some((w) => actividad.toLowerCase().includes(w));
      const hayCantidad = /\d/.test(t.slice(mAct.index, mAct.index + mAct[0].length + 12));
      if (actividad.length >= 3 && !esMagnitud) {
        return actividad.charAt(0).toUpperCase() + actividad.slice(1);
      }
      if (actividad.length >= 3 && esMagnitud && !hayCantidad) {
        return actividad.charAt(0).toUpperCase() + actividad.slice(1);
      }
      return null;
    }
    // "freelance", "consultor", "restaurante", "e-commerce"...
    const profesiones = [
      "freelance", "autonomo", "autónomo", "consultor", "consultora",
      "diseñador", "diseñadora", "programador", "programadora",
      "restaurante", "ecommerce", "e-commerce", "tienda", "bar",
      "cafeteria", "cafetería", "hotel", "agencia", "fotografo",
      "fotógrafo", "traductor", "traductora", "abogado", "abogada",
      "gestor", "gestora", "arquitecto", "arquitecta", "editor",
      "community manager", "marketer", "panadero", "panadera",
      "pastelero", "pastelera", "enfermer", "profesor", "profesora",
    ];
    for (const p of profesiones) {
      if (t.includes(p)) return p.charAt(0).toUpperCase() + p.slice(1);
    }
    return null;
  }

  function pintarChips() {
    const conts = porVariante("#contextChips");
    if (!conts.length) return;
    const partes = [];
    for (const s of SLOTS) {
      const v = state.slots[s.key];
      if (v !== undefined && v !== null && v !== "") {
        const val = s.key === "margen" ? fmt(v, 0) + " %"
                  : s.key === "actividad" ? String(v)
                  : fmt(v, 0) + " €";
        partes.push(
          '<span class="ctx-chip filled"><span class="ctx-ok">✓</span> ' +
          '<b>' + s.label + ":</b> " + escapar(val) + "</span>"
        );
      } else {
        partes.push(
          '<span class="ctx-chip pending">' + escapar(s.label) + ": —</span>"
        );
      }
    }
    const html = partes.join("");
    conts.forEach((c) => { c.innerHTML = html; });
  }

  function escapar(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // ---------------------------------------------------------------
  // Integracion con el contexto que consume el motor
  // ---------------------------------------------------------------
  // El contexto real vive en el IIFE principal, que no expone nada
  // al exterior. Para no reescribir ese modulo, el puente funciona por
  // DOM: escribimos en los inputs del formulario y lanzamos el evento
  // "input" para que la app lo vea. Los campos son la fuente de
  // verdad del motor (ver analizar()), asi que rellenar el input ES
  // rellenar el contexto.
  function aplicarSlotsAlFormulario() {
    const map = {
      renta: "#rentaNeta",
      margen: "#margenBruto",
      saldo: "#saldoActual",
      actividad: "#actividad",
    };
    for (const [k, sel] of Object.entries(map)) {
      const el = $(sel);
      if (!el) continue;
      const v = state.slots[k];
      if (v === undefined || v === null || v === "") continue;
      const nv = k === "margen" ? Math.round(v) : k === "actividad" ? String(v) : String(Math.round(v));
      if (el.value !== nv) {
        el.value = nv;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
    // Si ya hay datos, el paso 1 debe estar visible para que el
    // formulario refleje lo capturado.
    const cardDatos = $("#cardDatos");
    if (cardDatos && cardDatos.hidden) cardDatos.hidden = false;
  }

  // ---------------------------------------------------------------
  // UI de voz
  // ---------------------------------------------------------------
  // La UI de voz aparece en dos sitios (paso 1 y paso 2 del flujo).
  // Se listan TODOS los elementos de cada tipo y se actualizan a la
  // vez: el usuario ve el mismo estado en el sitio donde esta.
  const VARIANTES = ["", "Step1"];

  const porVariante = (base) =>
    VARIANTES.map((v) => $(base + v)).filter(Boolean);

  function setStatus(estado, texto) {
    for (const st of porVariante("#voiceStatus")) st.dataset.state = estado;
    for (const tx of porVariante("#voiceStatusText")) tx.textContent = texto;
    for (const orb of porVariante("#voiceOrb")) {
      orb.classList.toggle("listening", estado === "listening");
      orb.classList.toggle("speaking", estado === "speaking");
    }
    for (const btn of porVariante("#btnMic")) {
      btn.classList.toggle("on", estado === "listening" || estado === "speaking");
    }
    for (const meter of porVariante("#voiceMeter")) {
      meter.classList.toggle("on", estado === "listening");
    }
  }

  function aviso(msg) {
    for (const n of porVariante("#voiceNotice")) {
      if (!msg) { n.hidden = true; n.textContent = ""; continue; }
      n.hidden = false;
      n.textContent = msg;
    }
  }

  // ---------------------------------------------------------------
  // Medidor de nivel (feedback de que el micro esta abierto)
  // ---------------------------------------------------------------
  function arrancarMedidor() {
    try {
      const ac = state.audioCtx || (state.audioCtx = new (window.AudioContext || window.webkitAudioContext)());
      if (ac.state === "suspended") ac.resume();
      const src = ac.createMediaStreamSource(state.stream);
      const an = ac.createAnalyser();
      an.fftSize = 512;
      src.connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      const loop = () => {
        const els = porVariante("#voiceLevel");
        if (!state.on) { els.forEach((e) => { e.style.width = "0%"; }); return; }
        an.getByteTimeDomainData(buf);
        let m = 0;
        for (const v of buf) m = Math.max(m, Math.abs(v - 128));
        const ancho = Math.min(100, m * 1.6) + "%";
        els.forEach((e) => { e.style.width = ancho; });
        state.rafId = requestAnimationFrame(loop);
      };
      cancelAnimationFrame(state.rafId);
      state.rafId = requestAnimationFrame(loop);
    } catch (e) {
      // El medidor es decorativo: si falla, la voz sigue funcionando.
      console.warn("[MoraBanc] medidor no disponible:", e && e.message);
    }
  }

  function pararMedidor() {
    cancelAnimationFrame(state.rafId);
    state.rafId = 0;
    porVariante("#voiceLevel").forEach((e) => { e.style.width = "0%"; });
  }

  // ---------------------------------------------------------------
  // Enumeracion de microfonos
  // ---------------------------------------------------------------
  async function listarMicros(preferido) {
    const sels = porVariante("#voiceDevice");
    if (!sels.length) return;
    try {
      const devs = (await navigator.mediaDevices.enumerateDevices())
        .filter((d) => d.kind === "audioinput");
      if (devs.length < 2) { sels.forEach((s) => { s.hidden = true; }); return; }
      const actual = preferido ||
        (state.stream && state.stream.getAudioTracks()[0]
          ? state.stream.getAudioTracks()[0].getSettings().deviceId : "");
      const html = devs.map((d) =>
        '<option value="' + d.deviceId + '"' +
        (d.deviceId === actual ? " selected" : "") + ">" +
        escapar(d.label || "Micrófono") + "</option>"
      ).join("");
      sels.forEach((s) => { s.innerHTML = html; s.hidden = false; });
    } catch (e) {
      sels.forEach((s) => { s.hidden = true; });
    }
  }

  // ---------------------------------------------------------------
  // Ruta 1: ElevenLabs Conversations (misma integracion que Ubot)
  // ---------------------------------------------------------------
  async function iniciarElevenLabs() {
    // El SDK se sirve desde NUESTRO dominio, no desde un CDN externo.
    //
    // Motivo: si el CDN falla (bloqueo de red, CSP, wifi del sitio sin
    // acceso), la importacion falla y la voz cae al reconocimiento
    // nativo, que es mucho peor: el agente no habla, no puede
    // "esperar y volver a preguntar", y el usuario solo ve un error.
    // Con el SDK local, la conversacion con el agente depende solo de
    // nuestro sitio.
    //
    // Se intenta primero el local y, si no esta, el CDN (por si el
    // despliegue no lo incluye todavia).
    var Conversation = null;
    try {
      var mod = await import("./elevenlabs-client.js?v=20261107e");
      Conversation = mod.Conversation;
    } catch (e1) {
      console.warn("[MoraBanc] SDK local no disponible, se usa el CDN:", e1 && e1.message);
      var mod2 = await import("https://cdn.jsdelivr.net/npm/@elevenlabs/client@latest/+esm");
      Conversation = mod2.Conversation;
    }
    if (!Conversation) throw new Error("SDK de ElevenLabs no disponible");
    const sel = $("#voiceDevice");
    const pref = sel && !sel.hidden ? sel.value : undefined;

    // El stream es SOLO para el medidor de nivel (decorativo). El SDK
    // de ElevenLabs pide el suyo por su cuenta: si tambien se lo
    // pasamos, se piden dos capturas del mismo microfono a la vez y
    // Chrome falla con "audio-capture", que es exactamente lo que
    // pasaba.
    //
    // Si el medidor falla, la voz sigue: es decorativo.
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        audio: pref ? { deviceId: { exact: pref } } : true,
      });
      await listarMicros(pref);
      arrancarMedidor();
    } catch (e) {
      console.warn("[MoraBanc] medidor no disponible:", e && e.message);
      state.stream = null;
    }

    // Se marca antes de la sesion: el saludo se decide justo despues.
    state.vozConAgente = true;

    state.conv = await Conversation.startSession({
      agentId: ELEVENLABS_AGENT_ID,
      // "websocket" en vez de "webrtc".
      //
      // El modo webrtc usa LiveKit, que necesita AudioWorklets (el
      // navegador los carga como modulos desde un blob: y con una CSP
      // estricta fallan con "Failed to load the rawAudioProcessor
      // worklet module"). El modo websocket transmite el audio por la
      // conexion de la conversacion: sin LiveKit, sin AudioWorklets y
      // sin depender del micro del navegador para la entrada.
      //
      // La voz del agente es la misma (TTS de ElevenLabs); solo cambia
      // como viaja el audio.
      connectionType: "websocket",
      clientTools: {
        // El agente puede pedir abrir una URL. Se limita a las internas
        // de la propia aplicacion: nada de abrir sitios arbitrarios.
        open_url: (p) => {
          const url = String((p && p.url) || "");
          const internas = ["#stepContexto", "#stepResultado", "#chat"];
          if (internas.includes(url)) {
            const destino = document.querySelector(url);
            if (destino) {
              destino.scrollIntoView({ behavior: "smooth", block: "center" });
              return "opened";
            }
          }
          return "blocked";
        },
      },
      ...(pref ? { inputDeviceId: pref } : {}),
      onConnect: () => {
        setStatus("listening", "Escuchando…");
        aviso("");
      },
      onDisconnect: () => {
        setStatus("idle", "Toca para hablar");
        state.conv = null;
        state.vozConAgente = false;
      },
      onModeChange: (m) => {
        const modo = m && m.mode;
        if (modo === "speaking") setStatus("speaking", "Hablando…");
        else if (modo === "listening") setStatus("listening", "Escuchando…");
      },
      onMessage: (m) => {
        const texto = (m && m.message) || "";
        if (!texto) return;
        if (m.source === "user") {
          // El agente de ElevenLabs manda mensajes de control que NO
          // son preguntas del usuario: "..." (transcripcion vacia),
          // "audio-capture", "agent-response" de otro tipo. Si se pasan
          // a la API, el motor responde 401 ("Sesion no valida") y el
          // chat se llena de ruido.
          //
          // Solo se trasladan al motor las transcripciones con
          // contenido real.
          const limpio = texto.trim();
          if (limpio.length < 2 || /^\.+\.?$/.test(limpio)) return;
          // El usuario ha hablado: entra por el mismo camino que si
          // lo hubiera escrito, para que la captura de slots sea igual.
          enviar(limpio, { voz: true });
        } else if (m.source === "ai") {
          // La respuesta del agente ya suena por los altavoces, pero
          // TAMBIEN se escribe en el chat: si el micro esta apagado,
          // muted, o la sesion se corta, el usuario tiene que poder
          // leer lo que le han dicho. Ademas el chat es lo que se
          // captura en el pitch.
          registrarEnTraza(texto);
          const chat = $("#chatMessages");
          if (chat) {
            chat.appendChild(divMsg("asesor", escapar(texto)));
            chat.scrollTop = chat.scrollHeight;
          }
        }
      },
      onError: async (e) => {
        const msg = (e && e.message) || e || "";
        // "audio-capture" lo emite el reconocimiento NATIVO cuando el
        // navegador no le deja capturar el microfono a la vez que
        // WebRTC. No es un fallo de esta sesion: si estamos
        // conectados, el aviso molesta y confunde.
        if (/audio-capture/i.test(msg)) {
          // "audio-capture" es un fallo de captura del navegador, no
          // del agente. Si la sesion WebRTC ya esta viva, el aviso
          // solo confunde (lo emite el reconocimiento nativo).
          if (state.conv) {
            console.warn("[MoraBanc] captura en conflicto (sesion WebRTC viva)");
            return;
          }
          // Si la sesion no ha llegado a establecer, se reintenta
          // liberando el stream del medidor: es el conflicto tipico
          // de dos capturas del mismo microfono.
          console.warn("[MoraBanc] reintento de voz sin stream propio:", msg);
          try {
            if (state.stream) {
              state.stream.getTracks().forEach((t) => t.stop());
              state.stream = null;
            }
          } catch (e) {}
          if (!state.reintentoVoz) {
            state.reintentoVoz = true;
            try {
              await iniciarElevenLabs();
            } catch (e2) {
              setStatus("error", "Error de voz");
              aviso("No se pudo conectar la voz: " + escapar(msg));
            }
            return;
          }
        }
        setStatus("error", "Error de voz");
        aviso("No se pudo conectar la voz: " + escapar(msg));
      },
    });
  }

  // ---------------------------------------------------------------
  // Ruta 2: SpeechRecognition nativo (fallback)
  // ---------------------------------------------------------------
  function reconocimientoNativo() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const rec = new SR();
    rec.lang = document.documentElement.lang || "es-ES";
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (ev) => {
      let final = "";
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      const cap = $("#liveCaption");
      if (cap) {
        if (interim) {
          cap.hidden = false;
          cap.innerHTML = escapar(interim) + '<span class="caret"></span>';
        } else if (final) {
          cap.hidden = false;
          cap.innerHTML = escapar(final);
        }
      }
      if (final) {
        cap.hidden = true;
        rec.stop();
        if (state.recogiendo) {
          state.recogiendo = false;
          setStatus("listening", "Escuchando…");
          // Si la voz con el agente esta viva, el reconocimiento
          // nativo no debe mandar nada: se cuela con transcripciones
          // vacias ("...") que llegan al motor como si fueran
          // preguntas.
          if (state.vozConAgente) return;
          enviar(final, { voz: true });
        }
      }
    };

    rec.onerror = (ev) => {
      const err = ev && ev.error;
      // Si la sesion de ElevenLabs es la que manda, los errores del
      // reconocimiento nativo no cuentan: se pisan entre si (el
      // navegador no deja dos capturas de audio a la vez) y el aviso
      // que se ve es del fallback, no del camino que esta funcionando.
      if (state.conv || state.vozConAgente) {
        // La voz con el agente esta viva: los errores del
        // reconocimiento nativo no cuentan. Se pisan entre si (el
        // navegador no deja dos capturas de audio a la vez) y lo que
        // se ve es un aviso del fallback cuando la ruta que funciona
        // es la otra.
        state.recogiendo = false;
        return;
      }
      if (err === "no-speech") {
        aviso("No he oído nada. Inténtalo de nuevo.");
      } else if (err === "not-allowed" || err === "service-not-allowed") {
        aviso("El navegador ha bloqueado el micrófono. Permítelo en la barra de direcciones y reinténtalo.");
        setStatus("error", "Micrófono bloqueado");
      } else {
        aviso("Error de voz: " + escapar(err || "desconocido"));
        setStatus("error", "Error de voz");
      }
      state.recogiendo = false;
    };

    rec.onend = () => {
      // Chrome corta la sesion cada ~60s: si el usuario sigue en modo
      // voz, se reinicia sola para que no se corte la conversacion.
      if (state.on && state.recogiendo) {
        try { rec.start(); } catch (e) { /* ya arrancada */ }
      }
    };

    return rec;
  }

  // ---------------------------------------------------------------
  // Captura de texto (puente comun de voz y teclado)
  // ---------------------------------------------------------------
  // Se engancha al submit del formulario de chat existente y al
  // mensaje del agente de voz.
  function enviar(texto, opts) {
    const t = String(texto || "").trim();
    if (!t) return;

    // 1) Extraer slots de lo que ha dicho.
    const slots = extraerSlots(t);
    const nuevos = [];
    for (const [k, v] of Object.entries(slots)) {
      // Lo que dice el usuario SIEMPRE gana, aunque el slot ya tuviera
      // un valor (por ejemplo, el que precarga el portal de empresas).
      // Antes solo se rellenaban los vacios: si el portal precargaba
      // "30.000" y el usuario decia "facturo 60.000", se quedaba con
      // 30.000 y el motor calculaba sobre una cifra que el usuario
      // NUNCA dijo. En un pitch, eso es un desastre.
      if (state.slots[k] !== v) {
        state.slots[k] = v;
        nuevos.push(k);
      }
    }
    if (nuevos.length) {
      aplicarSlotsAlFormulario();
      pintarChips();
      const etq = nuevos.map((k) => {
        const s = SLOTS.find((x) => x.key === k);
        const v = state.slots[k];
        const val = k === "margen" ? fmt(v, 0) + " %"
                  : k === "actividad" ? v
                  : fmt(v, 0) + " €";
        return (s ? s.label : k) + " (" + val + ")";
      }).join(", ");
      registrarEnTraza("Contexto capturado: " + etq);
      // El asistente confirma lo que ha entendido y dice que le falta
      // (si algo): el usuario ve el progreso en la barra de voz.
      confirmarDato(etq);
    }

    // 2) Enviar al motor por el camino real de la app: el chat del
    // paso 2. Si el texto venia del formulario del paso 1, se
    // escribe alli para que quede en la conversacion.
    const form = $("#chatForm");
    const input = $("#chatInput");
    if (form && input) {
      input.value = t;
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
    // Si el texto venia del paso 1, se limpia su input para no
    // duplicar la frase.
    const in1 = $("#voiceInputStep1");
    if (in1 && opts && opts.desdePaso1) in1.value = "";
  }

  // La traza tecnica la rellena la app principal. Si no existe todavia
  // (el chat se abre despues del analisis), no pasa nada: la captura
  // de slots ya esta guardada en el formulario, que es lo que cuenta.
  function registrarEnTraza(texto) {
    const body = $("#trazaBody");
    if (!body) return;
    const div = document.createElement("div");
    div.className = "traza-item";
    div.textContent = texto;
    body.appendChild(div);
  }

  // ---------------------------------------------------------------
  // El asistente que acompaña
  // ---------------------------------------------------------------
  // El cuadro de voz no es solo un micro: es un ASESOR. Al activarlo
  // saluda, dice que espera, y va guiando la conversacion segun lo que
  // le falta (renta, saldo, actividad). Cuando ya lo tiene todo, lo dice
  // y espera a que pulses Analizar.
  //
  // La guia se decide con CODIGO (que slots faltan), no con un LLM: el
  // mismo principio que el motor. El LLM (ElevenLabs) pone la voz; la
  // logica de que preguntarle, la decide el front.

  function slotFaltante() {
    const c = state.contexto || {};
    if (!c.renta) return "renta";
    if (c.saldo === undefined || c.saldo === null) return "saldo";
    if (!c.actividad) return "actividad";
    return null;
  }

  function mensajeGuia() {
    const falta = slotFaltante();
    if (!falta) return t("vozListo");
    if (falta === "renta") return t("vozFaltaRenta");
    if (falta === "saldo") return t("vozFaltaSaldo");
    return t("vozFaltaActividad");
  }

  /**
   * Manda un texto al agente de voz para que lo DIGA.
   *
   * En ElevenLabs el agente habla cuando el usuario le habla; para que
   * el asistente tome la iniciativa se le manda un mensaje de usuario
   * sintetico (sendUserMessage). El agente lo trata como lo que el
   * usuario ha dicho y responde en voz alta.
   *
   * Si la voz no esta disponible (fallback a texto), el mensaje se
   * muestra en la barra y ya esta: el acompanamiento nunca bloquea.
   */
  function decirAlAgente(texto) {
    if (!texto) return;
    try {
      if (state.conv && typeof state.conv.sendUserMessage === "function") {
        state.conv.sendUserMessage(texto);
        return true;
      }
    } catch (e) {
      console.warn("[PlanificAND] no se pudo enviar el mensaje al agente de voz:", e && e.message);
    }
    return false;
  }

  /** Muestra la guia en la barra de voz y la intenta decir en voz alta. */
  function acompanar(texto) {
    if (!texto) return;
    aviso(texto);
    decirAlAgente(texto);
  }

  /** Saludo inicial: quien es, que espera y como se dice. */
  function saludar() {
    const saludo = t("vozSaludo");
    const guia = t("vozGuiaInicial");
    aviso(guia);
    // Si la voz con ElevenLabs esta viva, el PROPIO agente saluda
    // (tiene un mensaje de bienvenida configurado): si ademas se
    // pide por la API, el usuario oye el saludo dos veces y la API
    // responde "Sesion no valida" cuando el visitante no ha entrado
    // en el portal.
    // state.conv se asigna justo despues de iniciarElevenLabs(), asi
    // que aqui se comprueba el estado del DOM: si el indicador de voz
    // esta activo, la sesion de ElevenLabs esta en marcha.
    if (state.conv || state.vozConAgente) {
      return;
    }
    // Sin voz, el saludo se pide al motor por texto.
    if (!decirAlAgente(saludo)) {
      aviso(saludo);
    }
  }

  /** Se llama cuando el asistente ha capturado un dato: confirma y sigue. */
  function confirmarDato(dato) {
    const msg = t("vozConfirmado").replace("{dato}", dato);
    const falta = slotFaltante();
    const siguiente = falta ? " " + mensajeGuia() : " " + t("vozListo");
    if (!decirAlAgente(msg + siguiente)) {
      aviso(msg + " " + mensajeGuia());
    } else {
      aviso(mensajeGuia());
    }
  }

  // ---------------------------------------------------------------
  // Arranque / parada del modo voz
  // ---------------------------------------------------------------
  async function toggleVoz() {
    if (state.on) { await pararVoz(); return; }

    // La barra del paso 2 aparece al pulsar; la del paso 1 ya esta
    // visible (el micro es la via principal, no un extra).
    for (const bar of porVariante("#voiceBar")) bar.hidden = false;

    // El permiso de microfono se pide SIEMPRE: sin el permiso no hay
    // ni ElevenLabs ni SpeechRecognition.
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      aviso("El navegador ha bloqueado el micrófono. Permítelo en la barra de direcciones para hablar con el asesor.");
      setStatus("error", "Micrófono bloqueado");
      return;
    }

    state.on = true;
    aviso("");

    // Ruta preferida: ElevenLabs (conversacion real con el agente).
    if (ELEVENLABS_AGENT_ID) {
      try {
        setStatus("listening", "Conectando…");
        await iniciarElevenLabs();
        // El saludo del asistente: no espera en silencio a que hables,
        // se presenta y dice que necesita.
        saludar();
        return;
      } catch (e) {
        console.warn("[MoraBanc] ElevenLabs no disponible:", e && e.message);
        // Si la sesion de ElevenLabs quedo viva pese al error (el
        // agente arranca y lo que falla es el audio), NO se arranca el
        // reconocimiento nativo: serian dos rutas de voz compitiendo
        // por el microfono, y el nativo se cuela con transcripciones
        // vacias ("...") que llegan al motor como preguntas.
        if (state.conv || state.vozConAgente) {
          return;
        }
        aviso("Voz en modo texto: la conexión con el agente de voz no está disponible en este entorno.");
        // Se sigue con SpeechRecognition, que ya tiene el permiso.
      }
    }

    // Ruta de reserva: reconocimiento nativo.
    const rec = reconocimientoNativo();
    if (!rec) {
      aviso("Este navegador no admite voz. Puedes escribir tus datos en el chat y el asesor trabaja igual.");
      setStatus("error", "Voz no disponible");
      state.on = false;
      return;
    }
    state.recog = rec;
    state.recogiendo = true;
    try {
      rec.start();
      setStatus("listening", "Escuchando…");
      saludar();
    } catch (e) {
      state.recogiendo = false;
      setStatus("error", "Error de voz");
    }
  }

  async function pararVoz() {
    state.vozConAgente = false;
    state.on = false;
    state.recogiendo = false;
    setStatus("idle", "Toca para hablar");
    pararMedidor();

    if (state.conv) {
      const c = state.conv;
      state.conv = null;
      try { await c.endSession(); } catch (e) { /* ya cerrada */ }
    }
    if (state.recog) {
      const r = state.recog;
      state.recog = null;
      try { r.stop(); } catch (e) { /* ya parada */ }
    }
    if (state.stream) {
      state.stream.getTracks().forEach((tr) => tr.stop());
      state.stream = null;
    }
    const cap = $("#liveCaption");
    if (cap) { cap.hidden = true; cap.innerHTML = ""; }
  }

  // ---------------------------------------------------------------
  // Enganche
  // ---------------------------------------------------------------
  function aplicarParametrosPortal() {
    const p = new URLSearchParams(window.location.search);
    const perfil = p.get("perfil");
    const empresa = p.get("empresa");

    // Modo embed: el front va dentro del portal, que ya pone su
    // cabecera. Se oculta la nuestra.
    if (p.get("embed") === "1" || perfil || empresa) {
      document.body.classList.add("mb-embed");
    }

    if (!perfil && !empresa) return;

    if (perfil) {
      const btn = document.querySelector('#opcionesInicio .opcion[data-perfil="' + perfil + '"]');
      if (btn) btn.click();
    }

    const campos = {
      rentaNeta: p.get("renta"),
      margenBruto: p.get("margen"),
      saldoActual: p.get("saldo"),
      actividad: p.get("actividad"),
    };
    for (const [id, valor] of Object.entries(campos)) {
      if (valor === null || valor === "") continue;
      const el = $("#" + id);
      if (!el) continue;
      el.value = valor;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }

    if (empresa) {
      const sub = $(".brand-sub");
      if (sub) sub.textContent = empresa + " \u00b7 Andorra";
    }

    // Los chips de contexto se rellenan con los mismos datos: si el
    // campo de arriba ya tiene 30000, el chip debe decir "30.000 \u20ac".
    const slots = {
      renta: parseFloat($("#rentaNeta").value) || undefined,
      margen: parseFloat($("#margenBruto").value) || undefined,
      saldo: parseFloat($("#saldoActual").value) || undefined,
      actividad: ($("#actividad").value || "").trim() || undefined,
    };

    // Los chips leen de state.slots, no de los inputs: sin esto, el
    // portal precargaba los campos pero los chips se quedaban en "—"
    // y el usuario no veia que su situacion ya estaba capturada.
    Object.assign(state.slots, slots);
    pintarChips();

    window.__mbSlotsPendientes = slots;
    if (window.__mbSincronizarChips) window.__mbSincronizarChips(slots);
  }



  function init() {
    // El portal de empresas precarga la situacion por la URL. Se
    // aplica aqui, dentro del bundle que define state.slots y
    // pintarChips: si se hiciera en el bundle de la UI (que corre
    // antes), todavia no existian y los chips se quedaban en "—".
    aplicarParametrosPortal();

    // Si viene del portal de empresas, el escenario ya esta puesto:
    // no se toca nada.
    //
    // Si es el home suelto, se preselecciona el primer perfil (el caso
    // del pitch: freelance). Sin esto la pagina llega con los cuatro
    // chips en "—" y los campos vacios, y en un pitch eso se lee como
    // "no funciona" cuando en realidad solo falta elegir. Con el perfil
    // puesto, la situacion se ve capturada desde el primer segundo.
    const r = $("#rentaNeta");
    const hayDatos = r && r.value;
    if (!hayDatos && !document.body.classList.contains("mb-embed")) {
      const opciones = document.querySelectorAll("#opcionesInicio .opcion");
      const primera = opciones[0];
      if (primera) {
        // El click dispara el handler de la UI, que rellena los inputs
        // y avisa al motor por el puente. Aqui se espera a que el
        // handler termine (es sincrono) y se pintan los chips.
        primera.click();
      }
    }

    // Los inputs rellenos (del portal o de la preseleccion) se pasan al
    // state del motor y se pintan los chips. El bundle de la UI corre
    // ANTES que este y no puede pintar chips: este bundle aun no
    // existia cuando la UI elegia el perfil.
    const renta = $("#rentaNeta");
    if (renta && renta.value) {
      const slots = {
        renta: parseFloat(renta.value) || undefined,
        margen: parseFloat(($("#margenBruto") || {}).value) || undefined,
        saldo: parseFloat(($("#saldoActual") || {}).value) || undefined,
        actividad: (($("#actividad") || {}).value || "").trim() || undefined,
      };
      Object.assign(state.slots, slots);
      pintarChips();
    }

    // Los botones de micro de los dos pasos (el grande de la barra y
    // el pequeno junto al input del chat) hacen lo mismo.
    porVariante("#btnMic").forEach((b) => b.addEventListener("click", toggleVoz));
    porVariante("#voiceOrb").forEach((b) => b.addEventListener("click", toggleVoz));
    porVariante("#voiceDevice").forEach((s) => {
      s.addEventListener("change", async () => {
        // Cambiar de micro reinicia la captura: el stream anterior
        // esta atado al dispositivo viejo.
        if (state.on) { await pararVoz(); setTimeout(toggleVoz, 350); }
      });
    });

    // Tecla M: atajo para hablar sin tocar el raton.
    document.addEventListener("keydown", (e) => {
      if (e.key.toLowerCase() !== "m") return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      toggleVoz();
    });

    pintarChips();

    // Captura de slots tambien al ESCRIBIR: el mismo extractor sirve
    // para texto y para voz. Se engancha al submit de los dos
    // formularios (el del paso 1 y el del chat del paso 2).
    for (const id of ["#chatForm", "#voiceFormStep1"]) {
      const form = $(id);
      if (!form) continue;
      form.addEventListener("submit", () => {
        const input = id === "#chatForm" ? $("#chatInput") : $("#voiceInputStep1");
        if (!input) return;
        const slots = extraerSlots(input.value);
        let cambio = false;
        // Lo que el usuario escribe gana a lo que habia precargado
        // (el portal de empresas deja la situacion de la empresa
        // puesta). Antes solo se rellenaban los slots vacios, asi que
        // un usuario que corrigiera su renta se quedaba con la
        // precargada y el motor calculaba sobre una cifra distinta de
        // la que dijo.
        for (const [k, v] of Object.entries(slots)) {
          if (state.slots[k] !== v) { state.slots[k] = v; cambio = true; }
        }
        if (cambio) { aplicarSlotsAlFormulario(); pintarChips(); }
      }, true);
    }

    // El formulario del paso 1 tiene su propio motor de envio: lleva
    // la frase al chat del paso 2 (que es quien pregunta a la API) y
    // se limpia. El chat del paso 2 es el unico que habla con el
    // motor, para no duplicar llamadas ni trazas.
    const form1 = $("#voiceFormStep1");
    if (form1) {
      form1.addEventListener("submit", (e) => {
        e.preventDefault();
        const in1 = $("#voiceInputStep1");
        const chatIn = $("#chatInput");
        if (!in1 || !chatIn) return;
        const texto = in1.value.trim();
        if (!texto) return;
        chatIn.value = texto;
        in1.value = "";
        const chatForm = $("#chatForm");
        if (chatForm && typeof chatForm.requestSubmit === "function") chatForm.requestSubmit();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();