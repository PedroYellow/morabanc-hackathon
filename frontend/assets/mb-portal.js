/* ============================================================
   MoraBanc Digital — portal de empresas (simulador)
   ============================================================
   Tres cosas:
     1. Cambio de pestana (la del asesor abre el motor).
     2. Escenario de empresa: cada usuario de prueba abre una empresa
        distinta, con sus cuentas, nominas y patrimonio. Los datos
        vienen de data/mb_escenarios.json.
     3. El asesor se mete en un iframe: el motor (index.html) no sabe
        nada del portal, y el portal no sabe nada del motor.
   ============================================================ */
(function () {
  "use strict";

  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.from(document.querySelectorAll(s)); };

  // ---------------------------------------------------------------
  // Parametros
  // ---------------------------------------------------------------
  var params = new URLSearchParams(window.location.search);

  // El codigo de empresa sale del token de Cognito (preferred_username).
  // La URL (?user=...) es solo el respaldo para el modo demo: con sesion
  // iniciada, el token manda, porque es lo que el banco firmo.
  function codigoDeLaSesion() {
    try {
      var t = localStorage.getItem("mb-token");
      if (!t) return null;
      var claims = JSON.parse(decodeURIComponent(t.split(".")[1] || "{}"));
      return claims.preferred_username || null;
    } catch (e) { return null; }
  }

  var usuario = (codigoDeLaSesion() ||
                 params.get("user") ||
                 (function () {
                   try { return localStorage.getItem("mb-codigo") || ""; } catch (e) { return ""; }
                 })() ||
                 "12TJ28").toUpperCase();

  // ---------------------------------------------------------------
  // Escenarios
  // ---------------------------------------------------------------
  var ESCENARIOS = null;

  function cargarEscenarios() {
    return fetch("data/mb_escenarios.json")
      .then(function (r) {
        if (!r.ok) throw new Error("no se pudieron cargar los escenarios");
        return r.json();
      })
      .then(function (d) {
        ESCENARIOS = d.escenarios || [];
        return ESCENARIOS;
      });
  }

  function escenarioPorUsuario(u) {
    if (!ESCENARIOS) return null;
    for (var i = 0; i < ESCENARIOS.length; i++) {
      if (ESCENARIOS[i].usuario === u) return ESCENARIOS[i];
    }
    return null;
  }

  function escenarioPorId(id) {
    if (!ESCENARIOS) return null;
    for (var i = 0; i < ESCENARIOS.length; i++) {
      if (ESCENARIOS[i].id === id) return ESCENARIOS[i];
    }
    return null;
  }

  // ---------------------------------------------------------------
  // Pintar el escenario
  // ---------------------------------------------------------------
  function aplicarEscenario(esc) {
    if (!esc) return;

    // Cabecera: nombre y NIF.
    var meta = $(".mb-portal-user-meta");
    if (meta) {
      meta.innerHTML =
        "<strong>" + esc.razon_social.split(" ")[0].toUpperCase() + " " +
        (esc.razon_social.split(" ")[1] || "") + "</strong>" +
        '<span class="mb-portal-nif">' + esc.nif + " - " + esc.empresa + "</span>";
    }
    var av = $(".mb-portal-avatar");
    if (av) av.textContent = esc.razon_social.charAt(0).toUpperCase();

    // Saludo.
    var h1 = $(".mb-hello h1");
    if (h1) h1.textContent = "Hola, " + esc.razon_social.split(" ")[0];

    // Patrimonio y cuentas.
    var valor = $(".mb-patrimoni-value");
    if (valor) valor.textContent = fmtEuro(esc.patrimonio_total);

    var tarjetas = $$(".mb-card");
    if (tarjetas.length >= 2) {
      var totalCuentas = esc.cuentas.reduce(function (s, c) { return s + c.saldo; }, 0);
      var totalTarjetas = esc.tarjetas.reduce(function (s, c) { return s + c.saldo; }, 0);
      tarjetas[0].querySelector(".mb-card-value").textContent = fmtEuro(totalCuentas);
      tarjetas[1].querySelector(".mb-card-value").textContent = fmtEuro(totalTarjetas);
    }

    // Si es una empresa con nomina, se dice en el resumen.
    var prom = $(".mb-asesor-sub");
    if (prom) {
      var texto = "El motor de decisions financeres de MoraBanc per a la teva empresa. " +
        "Pregunta en veu alta o escriu: calcula el CASS, l'IRPF, l'IGI i la teva tresoreria amb la normativa andorrana.";
      if (!esc.es_autonomo && esc.nomina_mensual > 0) {
        texto = "Empresa amb " + esc.empleados + " empleat" + (esc.empleados === 1 ? "" : "s") +
          " i una nomina de " + fmtEuro(esc.nomina_mensual) + "/mes. " +
          "El motor de decisions financeres de MoraBanc calcula el CASS, l'IRPF, l'IGI i la teva tresoreria. " +
          "Pregunta en veu alta o escriu.";
      }
      prom.textContent = texto;
    }
  }

  function fmtEuro(v) {
    var neg = v < 0;
    var abs = Math.abs(v);
    var s = abs.toFixed(2).replace(".", ",");
    // Millares con punto: 2.221,16
    var partes = s.split(",");
    partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (neg ? "-" : "") + partes.join(",") + " €";
  }

  // ---------------------------------------------------------------
  // Pestanas
  // ---------------------------------------------------------------
  function activarPestana(nombre) {
    $$(".mb-tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.tab === nombre);
    });
    $$(".mb-panel").forEach(function (p) {
      p.hidden = p.dataset.panel !== nombre;
    });
    // El asesor necesita altura cuando se muestra.
    if (nombre === "asesor") {
      var f = $("#frameAsesor");
      if (f) {
        try {
          f.contentWindow.dispatchEvent(new Event("resize"));
        } catch (e) {}
      }
    }
    try {
      sessionStorage.setItem("mb-tab", nombre);
    } catch (e) {}
  }

  $$(".mb-tab").forEach(function (t) {
    t.addEventListener("click", function () {
      activarPestana(t.dataset.tab);
    });
  });

  // ---------------------------------------------------------------
  // Ojo: mostrar/ocultar cifras sensibles
  // ---------------------------------------------------------------
  var btnOjo = $("#btnOjoPortal");
  if (btnOjo) {
    btnOjo.addEventListener("click", function () {
      var ocultos = $$("[data-oculto]");
      var ocultar = !ocultos.length || !ocultos[0].classList.contains("oculto");
      ocultos.forEach(function (el) { el.classList.toggle("oculto", ocultar); });
    });
  }

  // ---------------------------------------------------------------
  // Salir
  // ---------------------------------------------------------------
  var btnSortir = $("#btnSortir");
  if (btnSortir) {
    btnSortir.addEventListener("click", function () {
      window.location.href = "mb-login.html";
    });
  }

  // ---------------------------------------------------------------
  // Arranque
  // ---------------------------------------------------------------
  cargarEscenarios()
    .then(function () {
      var esc = escenarioPorUsuario(usuario);
      if (esc) {
        aplicarEscenario(esc);
        // El asesor recibe el escenario por la URL: el motor carga el
        // perfil de datos demo correspondiente y precarga la situacion.
        var frame = $("#frameAsesor");
        if (frame) {
          var sep = frame.src.indexOf("?") === -1 ? "?" : "&";
          // El "v" rompe la cache del navegador: nginx cachea los
          // assets 5 minutos y, sin esto, un despliegue nuevo no se
          // ve hasta que expira. En un pitch, eso es perder el
          // momento.
          frame.src = frame.src + sep +
            "v=" + Date.now() +
            "&perfil=" + encodeURIComponent(esc.perfil_motor) +
            "&escenario=" + encodeURIComponent(esc.id) +
            "&empresa=" + encodeURIComponent(esc.empresa) +
            "&renta=" + encodeURIComponent(esc.renta_neta) +
            "&margen=" + encodeURIComponent(esc.margen_bruto) +
            "&saldo=" + encodeURIComponent(esc.saldo_actual) +
            "&actividad=" + encodeURIComponent(esc.actividad);
        }
      }

      // Pestana inicial: la del asesor si venimos desde el pitch, si
      // no la primera.
      var tab = "posicion";
      try { tab = sessionStorage.getItem("mb-tab") || "posicion"; } catch (e) {}
      if (params.get("tab") === "asesor") tab = "asesor";
      activarPestana(tab);
    })
    .catch(function (e) {
      console.error("[MoraBanc portal] escenarios:", e);
      activarPestana("posicion");
    });
})();
