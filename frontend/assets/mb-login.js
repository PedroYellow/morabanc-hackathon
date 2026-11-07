/* ============================================================
   MoraBanc Digital — pantalla de acceso (simulador)
   ============================================================
   Los DATOS DE PRUEBA son los del portal real:
     usuario: 12TJ28
     empresa: 933845 - PEDRO ANDRE MIRANDA GOMES

   Con "12TJ28" se entra al PORTAL DE EMPRESAS, que es donde vive el
   asesor financiero. Con cualquier otro usuario se entra al portal de
   particulares (una version reducida, para comprobar que el asesor
   tambien funciona ahi).

   El password no se valida: es un simulador. Lo que importa es que
   el camino de datos de prueba lleve al sitio correcto.
   ============================================================ */
(function () {
  "use strict";

  var $ = function (s) { return document.querySelector(s); };

  var USUARIO_EMPRESA = "12TJ28";
  var PASSWORD_VALIDA = "MoraBanc2026";  // la que se sugiere en el simulator

  // ---------------------------------------------------------------
  // Mostrar / ocultar contrasenya
  // ---------------------------------------------------------------
  var btnOjo = $("#btnOjo");
  var pass = $("#pass");
  if (btnOjo && pass) {
    btnOjo.addEventListener("click", function () {
      var visible = pass.type === "text";
      pass.type = visible ? "password" : "text";
      btnOjo.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
    });
  }

  // ---------------------------------------------------------------
  // Tooltip de informacion
  // ---------------------------------------------------------------
  var btnInfo = $("#btnInfo");
  var tipInfo = $("#tipInfo");
  if (btnInfo && tipInfo) {
    btnInfo.addEventListener("click", function (e) {
      e.stopPropagation();
      tipInfo.hidden = !tipInfo.hidden;
    });
    document.addEventListener("click", function () { tipInfo.hidden = true; });
  }

  // ---------------------------------------------------------------
  // Teclado virtual
  // ---------------------------------------------------------------
  var TECLADO = [
    ["1","2","3","4","5","6","7","8","9","0"],
    ["q","w","e","r","t","y","u","i","o","p"],
    ["a","s","d","f","g","h","j","k","l","ñ"],
    ["z","x","c","v","b","n","m","-","_","."],
  ];

  var teclado = $("#teclado");
  var vkKeys = $("#vkKeys");
  var btnTeclado = $("#btnTeclado");

  if (vkKeys) {
    // Se escribe en el campo que tenga el foco (o en la contrasenya).
    for (var f = 0; f < TECLADO.length; f++) {
      for (var c = 0; c < TECLADO[f].length; c++) {
        (function (ch) {
          var b = document.createElement("button");
          b.type = "button";
          b.textContent = ch;
          b.addEventListener("click", function () {
            var campo = document.activeElement;
            if (!campo || (campo.tagName !== "INPUT")) campo = pass;
            if (!campo) return;
            var ini = campo.selectionStart != null ? campo.selectionStart : campo.value.length;
            var fin = campo.selectionEnd != null ? campo.selectionEnd : campo.value.length;
            campo.value = campo.value.slice(0, ini) + ch + campo.value.slice(fin);
            campo.focus();
            try { campo.setSelectionRange(ini + 1, ini + 1); } catch (e) {}
          });
          vkKeys.appendChild(b);
        })(TECLADO[f][c]);
        }
      }

    // Barra inferior: espacio, borrar y cerrar.
    var espacio = document.createElement("button");
    espacio.type = "button";
    espacio.className = "space";
    espacio.textContent = "espai";
    espacio.addEventListener("click", function () {
      var campo = document.activeElement && document.activeElement.tagName === "INPUT" ? document.activeElement : pass;
      if (!campo) return;
      var ini = campo.selectionStart != null ? campo.selectionStart : campo.value.length;
      campo.value = campo.value.slice(0, ini) + " " + campo.value.slice(campo.selectionEnd != null ? campo.selectionEnd : ini);
      campo.focus();
    });
    vkKeys.appendChild(espacio);

    var borrar = document.createElement("button");
    borrar.type = "button";
    borrar.className = "wide";
    borrar.textContent = "borrar";
    borrar.addEventListener("click", function () {
      var campo = document.activeElement && document.activeElement.tagName === "INPUT" ? document.activeElement : pass;
      if (!campo) return;
      var ini = campo.selectionStart != null ? campo.selectionStart : campo.value.length;
      if (ini === 0) return;
      campo.value = campo.value.slice(0, ini - 1) + campo.value.slice(ini);
      campo.focus();
      try { campo.setSelectionRange(ini - 1, ini - 1); } catch (e) {}
    });
    vkKeys.appendChild(borrar);
  }

  if (btnTeclado && teclado) {
    btnTeclado.addEventListener("click", function () {
      teclado.hidden = !teclado.hidden;
      if (!teclado.hidden && pass) pass.focus();
    });
  }
  var btnCerrar = $("#btnCerrarTeclado");
  if (btnCerrar && teclado) {
    btnCerrar.addEventListener("click", function () { teclado.hidden = true; });
  }

  // ---------------------------------------------------------------
  // Acceso
  // ---------------------------------------------------------------
  var form = $("#loginForm");
  var btnAcceder = $("#btnAcceder");
  var user = $("#user");
  var recordar = $("#recordar");

  // La contrasenya se rellena sola con la de prueba: el objetivo es
  // que el pitch sea "escribir el usuario y pulsar Accedir".
  if (pass) pass.value = PASSWORD_VALIDA;

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var u = (user && user.value ? user.value : "").trim().toUpperCase();

      if (!u) {
        if (btnAcceder) {
          btnAcceder.classList.add("error");
          btnAcceder.textContent = "Falta l'usuari";
          setTimeout(function () {
            btnAcceder.classList.remove("error");
            btnAcceder.textContent = "Accedir";
          }, 1800);
        }
        if (user) user.focus();
        return;
      }

      if (btnAcceder) {
        btnAcceder.disabled = true;
        btnAcceder.textContent = "Accedint…";
      }

      // Simula el tiempo de respuesta del banco (para que el pitch
      // parezca real).
      setTimeout(function () {
        var destino = (u === USUARIO_EMPRESA)
          ? "mb-empresas.html"    // portal de empresas, con el asesor
          : "mb-particulares.html"; // portal de particulares

        // "Recordar usuari" guarda el usuario en localStorage.
        try {
          if (recordar && recordar.checked) localStorage.setItem("mb-usuario", u);
          else localStorage.removeItem("mb-usuario");
        } catch (err) {}

        window.location.href = destino + "?user=" + encodeURIComponent(u);
      }, 900);
    });
  }

  // Recuperar el usuario guardado.
  try {
    var guardado = localStorage.getItem("mb-usuario");
    if (guardado && user && !user.value) user.value = guardado;
  } catch (e) {}
})();
