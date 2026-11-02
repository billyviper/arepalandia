#!/usr/bin/env python3
"""Agrega hashtags, palabras de búsqueda y texto alternativo a las publicaciones de Instagram.

Uso: python3 agente/seo.py            (actualiza plan.json en el lugar)
Los estados de WhatsApp no llevan hashtags: ahí no sirven.
"""
import json, os, re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
seo = json.load(open(os.path.join(RAIZ, "agente", "seo.json"), encoding="utf-8"))
ruta_plan = os.path.join(RAIZ, "plan.json")
plan = json.load(open(ruta_plan, encoding="utf-8"))


def productos_de(p):
    t = (p["titulo"] + " " + p.get("foto", "")).lower().replace("arepalandia", "")
    return [k for k, v in seo["productos"].items() if any(b in t for b in v["busca"])]


def sin_hashtags(texto):
    lineas = [l for l in texto.rstrip().split("\n") if not re.fullmatch(r"\s*(#\S+\s*)+", l)]
    lineas = [l for l in lineas if not l.startswith("📍 ")]
    return "\n".join(lineas).rstrip()


PRECIO = re.compile(r"\$\s?\d|\d+\s?(pesos|uyu)\b", re.I)
for p in plan["publicaciones"]:
    if "Instagram" not in p["donde"]:
        continue
    # Regla de Arepalandia: en Instagram no se publican precios. Se sacan las frases que los tengan.
    if PRECIO.search(p["texto"]):
        partes = re.split(r"(?<=[.!?])\s+", p["texto"])
        p["texto"] = " ".join(x for x in partes if not PRECIO.search(x))
        print("Aviso: saqué un precio del texto de", p["id"])
    prods = productos_de(p)
    tags = []
    for k in reversed(prods):
        tags += seo["productos"][k]["hashtags"][:1]
    if len(tags) < 2 and prods:
        tags += seo["productos"][prods[-1]]["hashtags"][1:2]
    # Instagram permite 5: producto (2) + lugar + rubro + marca
    tags = tags[:2] + seo["lugar"][:1] + seo["rubro"][:1] + seo["marca"]
    tags = list(dict.fromkeys(tags))[: seo["maximo_hashtags"]]
    frases = [seo["productos"][k]["frase"] for k in prods if seo["productos"][k]["frase"]]
    frase = frases[-1] if frases else "comida venezolana en Mercedes"
    # Instagram hoy busca por palabras del texto, no solo por hashtags: dejamos una línea con lo que la gente escribe.
    ubic = f"📍 {frase[0].upper() + frase[1:]}, Soriano. Delivery y para llevar."
    p["hashtags"] = tags
    p["texto"] = sin_hashtags(p["texto"]) + "\n\n" + ubic + "\n\n" + " ".join(tags)
    nombre = seo["productos"][prods[-1]]["nombre"] if prods else "Comida"
    if "Reel" in p["donde"]:
        p.pop("alt", None)
        continue
    p["alt"] = f"{nombre} de Arepalandia, comida venezolana en Mercedes, Uruguay. {p.get('alt_foto', '')}".strip()

plan["palabras_busqueda"] = seo["palabras_busqueda"]
plan["hashtags_banco"] = {"Lugar": seo["lugar"], "Comida venezolana": seo["rubro"], "Delivery": seo["servicio"] + seo["marca"],
                          **{k.capitalize(): v["hashtags"] for k, v in seo["productos"].items()}}
json.dump(plan, open(ruta_plan, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Listo:", sum(1 for p in plan["publicaciones"] if p.get("hashtags")), "publicaciones de Instagram con hashtags")
