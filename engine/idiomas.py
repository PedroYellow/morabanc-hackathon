"""
Idiomas: en que idioma habla el cliente y como se le responde.

El por que
----------
Andorra es un pais con tres lenguas oficiales (catalan, espanol y
frances) y en la practica hay clientes que hablan catalan, espanol,
frances, ingles, portugues, italiano, rumano, ruso, arabe o chino.

El producto no puede asumir el espanol. Pero el motor, la normativa y
las cifras son del banco: eso va SIEMPRE en espanol (es el idioma en el
que esta la normativa andorrana y el que el cliente entiende de sus
declaraciones).

La regla:
    - El motor, las cifras y la normativa: en espanol.
    - La conversacion con el cliente: en el idioma en el que habla.

Como se detecta
---------------
Por palabras clave del mensaje. No es perfecto (y no pretende ser),
pero para decidir "esta persona me esta hablando en portugues" hay
suficiente senal: "voce", "obrigado", "quanto custa" -> portugues;
"bonjour", "je voudrais" -> frances; "thank you", "how much" -> ingles;
"dobri den", "skolko" -> ruso.

Cuando hay duda, se responde en espanol, que es el idioma por defecto
del banco.

Los codigos son los de la API de ElevenLabs (el agent tiene
"language": "es" por defecto) y los codigos ISO 639-1.
"""

from __future__ import annotations

import re


#: Idiomas que el agente sabe manejar, con su nombre para el LLM.
IDIOMAS: dict[str, str] = {
    "es": "espanol",
    "ca": "catalan",
    "fr": "frances",
    "en": "ingles",
    "pt": "portugues",
    "it": "italiano",
    "ro": "rumano",
    "ru": "ruso",
    "ar": "arabe",
    "zh": "chino",
    "it_IT": "italiano",
}


#: Palabras que delatan el idioma. Cuantas mas, mas probable.
MARCAS: dict[str, tuple[str, ...]] = {
    "pt": (
        "obrigado", "obrigada", "bom dia", "boa tarde", "boa noite",
        "quanto custa", "quanto e", "como voce", "como esta", "nao",
        "quero", "preciso", "tenho", "a minha", "meu", "minha", "voce",
        "sim", "nao sei", "favor", "senhor", "senhora", "saude",
        "posso", "gostaria", "conseguir", "dinheiro", "casa", "carro",
    ),
    "fr": (
        "bonjour", "bonsoir", "salut", "merci", "comment allez", "je voudrais",
        "je veux", "combien", "ca cout", "s'il vous plait", "madame",
        "monsieur", "je ne sais pas", "avec plaisir", "besoin", "maison",
        "voiture", "argent", "salaire", "travail", "travaille",
    ),
    "en": (
        "thank you", "thanks", "how much", "how do i", "i would like",
        "i want", "i need", "good morning", "good evening", "good afternoon",
        "hello", "hi there", "please", "can i afford", "i don't know",
        "house", "car", "money", "salary", "work", "buy", "bought",
    ),
    "it": (
        "grazie", "buongiorno", "buonasera", "per favore", "quanto costa",
        "come stai", "vorrei", "ho bisogno", "non so", "casa", "macchina",
        "denaro", "lavoro", "signora", "signore", "ciao",
    ),
    "ro": (
        "buna ziua", "multumesc", "cat costa", "cum stai", "as vrea",
        "am nevoie", "nu stiu", "casa", "masina", "bani", "salariu",
        "lucrez", "va rog",
    ),
    "ru": (
        "привет", "здравствуйте", "спасибо", "сколько стоит", "как дела",
        "хочу купить", "нужно", "не знаю", "дом", "машина", "деньги",
        "зарплата", "работа",
    ),
    "ar": (
        "مرحبا", "السلام عليكم", "شكرا", "كم الثمن", "كيف حالك", "اريد",
        "أحتاج", "لا أعرف", "منزل", "سيارة", "مال", "راتب", "عمل",
    ),
    "zh": (
        "你好", "您好", "谢谢", "多少钱", "我想买", "需要", "不知道",
        "房子", "车", "钱", "工资", "工作",
    ),
    # El catalan comparte casi todas las palabras con el espanol, asi
    # que aqui solo van las que NO existen en espanol. Si no hay
    # ninguna, se responde en espanol (que es lo correcto: el
    # catalan y el espanol se distinguen por los articulos y las
    # terminaciones, no por el vocabulario basico).
    "ca": (
        "bon dia", "bona tarda", "bon vespre", "gracies", "quan costa",
        "com estas", "vull", "necessito", "cotxe", "diners", "treball",
        "em pots", "tinc", "em cal", "no se perquè", "què tal", "per què",
        "surt", "cada any", "ara mateix", "de fet", "tal qual",
    ),
}

#: Palabras que delatan espanol (para no confundirlas con catalan/portugues).
MARCAS_ES = (
    "hola", "gracias", "cuanto", "cuanta", "cuesta", "necesito", "quiero",
    "tengo", "casa", "coche", "carro", "dinero", "salario", "trabajo",
    "buenos dias", "buenas tardes", "por favor", "no se", "se puede",
    "me queda", "puedo", "ayuda", "asesor", "banco", "eur", "que",
    "para", "con", "mi", "me", "de", "en",
)

#: Palabras que delatan catalan.
MARCAS_CA = (
    "bon dia", "bona tarda", "bon vespre", "gracies", "quan costa", "com estàs",
    "vull", "necessito", "no sé", "cotxe", "diners", "salari", "treball",
    "puc", "tinc", "em pots",
)

#: Indicios de catalan frente a espanol (palabras que solo son catalanas).
SOLO_CA = (
    "vull", "necessito", "cotxe", "diners", "treball", "em pots", "tinc",
    "em cal", "què tal", "per què", "ara mateix", "de fet", "tal qual",
    "gracies", "bon dia", "bona tarda", "surt", "cada any",
)

#: Indicios de espanol frente a catalan.
SOLO_ES = (
    "quiero", "necesito", "coche", "carro", "dinero", "salario", "trabajo",
    "puedo", "tengo", "gracias", "hola", "buenos dias", "buenas tardes",
    "me queda", "asesor",
)


def detectar_idioma(texto: str) -> tuple[str, float]:
    """
    Devuelve (codigo, confianza) del idioma del texto.

    La confianza va de 0 a 1. Por debajo de 0.25 se considera que no
    hay senal suficiente y se responde en espanol (el idioma por
    defecto del banco).
    """
    if not texto or not texto.strip():
        return "es", 0.0

    t = texto.lower()
    # Las marcas de mas de una palabra se buscan tal cual.
    puntuaciones: dict[str, int] = {}

    for codigo, marcas in MARCAS.items():
        puntos = 0
        for marca in marcas:
            if " " in marca:
                if marca in t:
                    puntos += 2
            else:
                # Palabra suelta: tiene que aparecer como palabra
                # completa (con limites), no como parte de otra.
                if re.search(r"(?<!\w)" + re.escape(marca) + r"(?!\w)", t):
                    puntos += 1
        if puntos:
            puntuaciones[codigo] = puntos

    # Catalan y espanol se pisan. Se desambigua por las palabras que
    # solo existen en uno de los dos.
    if "ca" in puntuaciones or "es" in puntuaciones:
        solo_ca = sum(1 for w in SOLO_CA if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t))
        solo_es = sum(1 for w in SOLO_ES if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t))
        # El catalan solo gana si tiene mas palabras propias que el
        # espanol. Con empate, gana el espanol: es el idioma por defecto
        # del banco y el que menos sorprende.
        if solo_ca > solo_es:
            puntuaciones["ca"] = puntuaciones.get("ca", 0) + solo_ca * 2
            puntuaciones.pop("es", None)
        else:
            puntuaciones["es"] = puntuaciones.get("es", 0) + solo_es * 2 + 1
            puntuaciones.pop("ca", None)

    if not puntuaciones:
        return "es", 0.0

    mejor = max(puntuaciones, key=lambda k: puntuaciones[k])
    total = sum(puntuaciones.values())
    confianza = min(1.0, puntuaciones[mejor] / max(2.0, total) * (1.0 + puntuaciones[mejor] * 0.1))
    confianza = min(1.0, confianza)

    if confianza < 0.25:
        return "es", confianza

    return mejor, confianza


def nombre_idioma(codigo: str) -> str:
    return IDIOMAS.get(codigo, codigo)


def instruction_de_idioma(codigo: str, confianza: float) -> str:
    """
    La instruccion que se mete en el prompt del agente para que
    responda en el idioma del cliente.

    Importante: las CIFRAS y las REGLAS se citan en espanol (es el
    idioma del banco), pero la prosa va en el idioma del cliente.
    """
    if codigo == "es" or confianza < 0.25:
        return (
            "IDIOMA: el cliente habla espanol. Responde en espanol."
        )

    nombre = nombre_idioma(codigo)
    return (
        f"IDIOMA: el cliente te esta hablando en {nombre.upper()}. "
        f"Respondele en {nombre}, con naturalidad (no traduzcas literalmente "
        f"del espanol: escribe como lo escribiria un {nombre} de verdad). "
        f"EXCEPTO: las cifras, los nombres de impuestos y las reglas "
        f"(CASS, IRPF, IGI, tramos) se citan tal cual, en espanol, que es "
        f"como estan en la normativa del banco y como las entiende en sus "
        f"declaraciones. Los porcentajes y los importes van con el formato "
        f"europeo (1.234,56 EUR)."
    )


def detectar_en_conversacion(mensajes: list[dict]) -> str:
    """
    El idioma de una conversacion entera.

    Se mira el ultimo mensaje del cliente (el que pesa) y, si hay duda,
    se mira el historial. Un cliente puede cambiar de idioma a mitad,
    pero se responde en el ultimo que ha usado.
    """
    if not mensajes:
        return "es"

    for m in reversed(mensajes):
        if m.get("source") == "user" and (m.get("message") or "").strip():
            codigo, conf = detectar_idioma(m["message"])
            if conf >= 0.35:
                return codigo
    return "es"
