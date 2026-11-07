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

   AUTENTICACION REAL (AWS Cognito)
   ---------------------------------------------------------------
   El login valida contra el user pool de Cognito de AWS:
     - El campo "usuario" acepta el codigo de empresa (12TJ28) o el
       email. El codigo se busca en el atributo preferred_username.
     - La contrasena se comprueba contra Cognito (USER_PASSWORD_AUTH).
     - Si la sesion es valida, se guarda el token y se entra al portal
       de empresas o de particulares segun el perfil del usuario.

   Si Cognito no esta disponible (sin red, o el pool no configurado),
   se cae al modo DEMO: se comprueba la contrasena de prueba y se entra
   igualmente. Es lo que permite que el pitch no se caiga nunca.

   Los 4 usuarios de prueba (creados en Cognito con
   admin-create-user) son:

     12TJ28  pedro.andre.miranda@morabanc-demo.ad      Freelance
     12TJ29  finanzas.andorradigital@morabanc-demo.ad  Quiere contratar
     12TJ30  admin.barnesifils@morabanc-demo.ad         Comercio
     12TJ31  finanzas.ceramicacanillo@morabanc-demo.ad  Cierre

   Contrasena de todos: MoraBanc2026!
   ============================================================ */
(function () {
  "use strict";

  var $ = function (s) { return document.querySelector(s); };

  // El codigo de empresa que abre el PORTAL DE EMPRESAS (donde vive el
  // asesor). Los demas usuarios de prueba van al portal de particulares.
  var USUARIO_EMPRESA = "12TJ28";
  var PASSWORD_VALIDA = "MoraBanc2026!";  // la de los usuarios de demo

  // Cognito (inyectado por el deploy; el front lo lee de window)
  var COGNITO_DOMAIN = (window.__COGNITO_DOMAIN__ || "").trim();
  var COGNITO_CLIENT = (window.__COGNITO_CLIENT_ID__ || "").trim();
  var REGION = (window.__AWS_REGION__ || "us-east-1").trim();

  // Los codigos de empresa de prueba y su email, para traducir el
  // codigo que escribe el usuario al email que usa Cognito.
  var EMAILS_DEMO = {
    "12TJ28": "pedro.andre.miranda@morabanc-demo.ad",
    "12TJ29": "finanzas.andorradigital@morabanc-demo.ad",
    "12TJ30": "admin.barnesifils@morabanc-demo.ad",
    "12TJ31": "finanzas.ceramicacanillo@morabanc-demo.ad",
  };

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
  // ---------------------------------------------------------------
  // Autenticacion contra Cognito
  // ---------------------------------------------------------------
  //
  //  El user pool exige email como nombre de usuario, pero el
  // Banco manda por codigo (12TJ28). Se traducen los codigos de
  //  prueba; si el usuario escribe un email, se usa tal cual.
  //
  //  Se usa la API de Cognito (InitiateAuth con USER_PASSWORD_AUTH)
  //  desde el navegador. El client de Cognito tiene permitidos los
  //  flujos de password (no hace falta implicit flow con redirect).

  function usuarioComoEmail(u) {
    var cod = String(u || "").trim().toUpperCase();
    if (EMAILS_DEMO[cod]) return EMAILS_DEMO[cod];
    if (cod.indexOf("@") > 0) return cod.toLowerCase();
    return null;
  }

  function autenticar(usuario, contrasena) {
    var email = usuarioComoEmail(usuario);
    if (!email) {
      return Promise.resolve({ ok: false, mensaje: "Usuari desconegut" });
    }
    if (!COGNITO_DOMAIN || !COGNITO_CLIENT) {
      // Sin configuracion de Cognito: modo demo.
      return Promise.resolve(
        contrasena === PASSWORD_VALIDA
          ? { ok: true, demo: true, empresa: String(usuario).toUpperCase() === USUARIO_EMPRESA }
          : { ok: false, mensaje: "Contrasenya incorrecta" }
      );
    }

    // La validacion la hace la Lambda (/api/login): ella llama a
    // Cognito con ADMIN_USER_PASSWORD_AUTH y devuelve el token ya
    // firmado. Asi el navegador nunca gestiona la contrasena contra
    // Cognito directamente y no hace falta el secret del cliente.
    var api = (window.__API_URL__ || "/api").replace(/\/$/, "");
    var cuerpo = new URLSearchParams();
    cuerpo.set("usuario", usuario);
    cuerpo.set("contrasena", contrasena);

    return fetch(api + "/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        usuario: usuario,
        contrasena: contrasena,
      }),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) {
            return { ok: false, mensaje: (j && j.error) || "Contrasenya incorrecta" };
          }
          var cod = j.codigo || "";
          if (!cod) {
            for (var k in EMAILS_DEMO) {
              if (EMAILS_DEMO[k] === email) { cod = k; break; }
            }
          }
          try {
            localStorage.setItem("mb-token", j.id_token || "");
            localStorage.setItem("mb-refresh", j.refresh_token || "");
            localStorage.setItem("mb-codigo", cod);
          } catch (e) {}
          return { ok: true, empresa: cod === USUARIO_EMPRESA, codigo: cod };
        });
      })
      .catch(function () {
        // Error de red: se propaga y el llamante cae al modo demo.
        throw new Error("sin red");
      });
  }

  function entrar(r) {
    var destino = (r.empresa || r.codigo === USUARIO_EMPRESA)
      ? "mb-empresas.html"      // portal de empresas, con el asesor
      : "mb-particulares.html"; // portal de particulares

    // "Recordar usuari" guarda el usuario en localStorage.
    try {
      var u = (user && user.value ? user.value : "").trim().toUpperCase();
      if (recordar && recordar.checked) localStorage.setItem("mb-usuario", u);
      else localStorage.removeItem("mb-usuario");
    } catch (err) {}

    window.location.href = destino +
      (r.codigo ? "?user=" + encodeURIComponent(r.codigo) : "");
  }

  // Acceso
  // ---------------------------------------------------------------
  var form = $("#loginForm");
  var btnAcceder = $("#btnAcceder");
  var user = $("#user");
  var recordar = $("#recordar");

  // La contrasenya NO se rellena sola: el login tiene que parecer real.
  // Para el pitch, el usuario escribe el codigo (12TJ28) y la
  // contrasenya de demo, que aparece en la propia pagina.
  if (pass) pass.value = "";

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

      // Autentica contra Cognito. Si no se puede (sin red, pool no
      // configurado), cae al modo demo.
      autenticar(u, pass ? pass.value : "")
        .then(function (r) {
          if (!r.ok) {
            if (btnAcceder) {
              btnAcceder.classList.add("error");
              btnAcceder.textContent = r.mensaje || "Error d'autenticacio";
              setTimeout(function () {
                btnAcceder.classList.remove("error");
                btnAcceder.textContent = "Accedir";
              }, 2200);
            }
            return;
          }
          entrar(r);
        })
        .catch(function () {
          // Fallo de red: modo demo, para que el pitch no se caiga.
          if (pass && pass.value === PASSWORD_VALIDA) {
            entrar({ demo: true, empresa: u === USUARIO_EMPRESA });
          } else {
            if (btnAcceder) {
              btnAcceder.classList.add("error");
              btnAcceder.textContent = "No s'ha pogut connectar";
              setTimeout(function () {
                btnAcceder.classList.remove("error");
                btnAcceder.textContent = "Accedir";
              }, 2200);
            }
          }
        });
    });
  }

  // Recuperar el usuario guardado.
  try {
    var guardado = localStorage.getItem("mb-usuario");
    if (guardado && user && !user.value) user.value = guardado;
  } catch (e) {}
})();
