"""Stage 02b: controls.

For each false friend proposed in stage 02, finds general Spanish words with
similar frequency (wordfreq Zipf) and length. That way a difference in
accuracy between false friends and controls is not explained just by some
words being more common than others (in the initial list the controls were
about 25 times more frequent than the false friends).

A word qualifies as a control if:
- it is in wordfreq and is a lemma in kaikki or Wikcionario, with some sense
  without a regional mark;
- no current sense is marked for the target variety, for a competitor (Spain,
  Mexico) or for a broad region (Latin America): the control has to mean the
  same here, in Spain and in Mexico;
- it is not in diccionarioargentino.com or among the candidates;
- it is not a proper name or a vulgarism, and it is a noun, verb, adjective
  or adverb;
- it is an everyday word: not an inflected form, an English loan (by
  etymology or by spelling) or a technical term.

Up to `por_falso_amigo` controls are kept per false friend (they also need a
song context in stage 03, and some will drop out) and a distinct main one is
assigned to each false friend.

Outputs:
- data/interim/controles.jsonl: one control per line, with its pairings.
- data/interim/emparejamientos_controles.csv: one false friend per line.
- data/interim/02b_controles_numeros.json: pairing and Zipf by layer.

Usage:
    python -m pipeline.stage02b_controls
"""

import bisect
import csv
import json
import os
import re
import statistics
from collections import Counter

from wordfreq import iter_wordlist, zipf_frequency

from pipeline import common, regions
from pipeline import stage01_candidates as s01
from pipeline import stage02_layer as s02

OUTPUT = os.path.join(common.DATA_INTERIM, "controles.jsonl")
PAIRINGS = os.path.join(common.DATA_INTERIM, "emparejamientos_controles.csv")
NUMBERS = os.path.join(common.DATA_INTERIM, "02b_controles_numeros.json")

# Regions that disqualify a control: it has to mean the same here, in Spain
# and in Mexico. "otra" (Chile, Andalusia) does not affect those three.
_NON_GENERAL_REGIONS = {"objetivo", "competidora", "amplia"}
# Spelling Spanish does not use: k or w, double consonants (except ll, rr, cc,
# nn) and endings in unusual consonants. Catches the anglicisms that kaikki
# does not mark as loans (fuzz, hot, cast, graffiti).
_FOREIGN_SPELLING = re.compile(r"[kw]|([bdfgmpstvz])\1|[bcfgkptvhw]$")
# Glosses of forms and spellings that Wikcionario does not always mark as
# "form of"
_NON_LEMMA_GLOSS = re.compile(r"^(Participio|Gerundio|Forma|Grafía|Variante|Plural|Femenino)\b")


def excluded_words(cfg):
    """Accent-free keys of everything that is rioplatense or already a
    candidate: the terms of the collaborative dictionary (with any score), the
    candidates and their variants."""
    excluded = set()
    for d in common.read_jsonl(s01.DEFINITIONS):
        for form in s01.lemma_forms(d["lema"] or d["titulo_indice"]):
            excluded.add(common.search_key(form))
    for c in common.read_jsonl(s01.OUTPUT):
        excluded.add(c["clave"])
        excluded.update(v["clave"] for v in c["variantes"])
    return excluded


def evaluate_word(word, sources, cfg):
    """Data of the control if the word qualifies, or None. Besides the region
    rules, a control has to be an everyday word, like the false friends: out
    go inflected forms (brota, abogando: their frequency is the verb's),
    homographs of proper names (brasil: wordfreq lowercases everything),
    English loans (gif, bypass) and technical terms (adenina, ascitis)."""
    ccfg = cfg["controles"]
    ignored = set(cfg["etapa02_capa"]["tags_ignorados"])
    excluded_tags = set(ccfg["tags_excluidos"])
    technical = set(ccfg["temas_tecnicos"])
    valid_pos = set(ccfg["pos_validas"])
    general_pos, glosses, ids = Counter(), {}, []
    for name, f in sources.items():
        if any(e["pos"] == "name" for e in f["indice"].get(word.capitalize(), [])):
            return None
        for e in f["indice"].get(word, []):
            if e.get("prestamo_ingles"):
                return None
            for a in e["acepciones"]:
                if a["forma_de"] or a["alt_de"] or \
                        any(_NON_LEMMA_GLOSS.match(g) for g in a["glosas"]):
                    return None
                tags = set(a["tags"])
                if tags & excluded_tags:
                    return None
                if tags & ignored or set(a.get("temas", [])) & technical:
                    continue
                region, _ = regions.sense_region(a, f["variedades"])
                if region in _NON_GENERAL_REGIONS:
                    return None
                if region == "general" and e["pos"] in valid_pos and a["glosas"]:
                    general_pos[e["pos"]] += 1
                    glosses.setdefault(name, "; ".join(a["glosas"]))
                    ids.append(a["id"])
    if not general_pos:
        return None
    return {
        "term": word,
        "pos": general_pos.most_common(1)[0][0],
        "zipf": zipf_frequency(word, "es"),
        "largo": len(word),
        # Spanish gloss if Wikcionario has one: useful for the options
        "glosa": glosses.get("wikcionario") or glosses.get("kaikki"),
        "fuente_glosa": "wikcionario" if "wikcionario" in glosses else "kaikki",
        "ids_acepciones": ids[:5],
    }


def build_pool(sources, cfg, excluded):
    ccfg = cfg["controles"]
    pool = []
    for word in iter_wordlist("es", wordlist="best"):
        if not word.isalpha() or len(word) < ccfg["largo_minimo"] or \
                _FOREIGN_SPELLING.search(word) or common.search_key(word) in excluded:
            continue
        control = evaluate_word(word, sources, cfg)
        if control:
            pool.append(control)
    pool.sort(key=lambda c: c["zipf"])
    return pool


def main_pos(layer):
    """Part of speech of the rioplatense sense; if no source has it, the most
    common one among all the senses."""
    target_pos = Counter(a["pos"] for n in ("kaikki", "wikcionario")
                         for a in layer[f"acepciones_{n}"]["objetivo"])
    if target_pos:
        return target_pos.most_common(1)[0][0]
    all_pos = Counter(a["pos"] for n in ("kaikki", "wikcionario")
                      for senses in layer[f"acepciones_{n}"].values() for a in senses)
    return all_pos.most_common(1)[0][0] if all_pos else None


def pair_controls(false_friends, pool, cfg):
    """Up to `por_falso_amigo` controls per false friend, sorted by same part
    of speech, closeness in Zipf and in length. Then assigns a distinct main
    one to each false friend, starting with those that have fewer options."""
    ccfg = cfg["controles"]
    tol_z, tol_l, k = ccfg["tolerancia_zipf"], ccfg["tolerancia_largo"], ccfg["por_falso_amigo"]
    zipfs = [c["zipf"] for c in pool]
    rows = []
    for fa in false_friends:
        z, length, pos = zipf_frequency(fa["term"], "es"), len(fa["term"]), main_pos(fa)
        row = {"fa": fa, "zipf": z, "largo": length, "pos": pos, "opciones": [], "motivo": ""}
        if z == 0:
            row["motivo"] = "no esta en wordfreq"
        else:
            start_idx, end_idx = bisect.bisect_left(zipfs, z - tol_z), bisect.bisect_right(zipfs, z + tol_z)
            nearby = [c for c in pool[start_idx:end_idx] if abs(c["largo"] - length) <= tol_l]
            nearby.sort(key=lambda c: (c["pos"] != pos, abs(c["zipf"] - z),
                                       abs(c["largo"] - length), c["term"]))
            row["opciones"] = nearby[:k]
            if not nearby:
                row["motivo"] = "sin palabras con Zipf y largo parecidos"
        rows.append(row)

    used = set()
    for row in sorted(rows, key=lambda f: (len(f["opciones"]), f["fa"]["clave"])):
        row["principal"] = next((c for c in row["opciones"] if c["term"] not in used), None)
        if row["principal"]:
            used.add(row["principal"]["term"])
        elif row["opciones"]:
            row["motivo"] = "sus opciones ya son principales de otro falso amigo"
    return rows


def summary(values):
    if not values:
        return None
    q = statistics.quantiles(values, n=4) if len(values) > 1 else [values[0]] * 3
    return {"n": len(values), "p25": round(q[0], 2), "mediana": round(statistics.median(values), 2),
            "p75": round(q[2], 2)}


def main():
    cfg = common.load_config()
    sources = {}
    for name, module, cfg_key in s02.LEXICAL_SOURCES:
        sources[name] = {"indice": module.index(cfg), "variedades": cfg[cfg_key]}

    layers = list(common.read_jsonl(s02.OUTPUT))
    false_friends = sorted((c for c in layers if c["capa_propuesta"] == "falso_amigo"),
                           key=lambda c: c["clave"])
    pool = build_pool(sources, cfg, excluded_words(cfg))
    print(f"control pool: {len(pool)} words")
    rows = pair_controls(false_friends, pool, cfg)

    # One control per line, with every false friend it serves.
    controls = {}
    for row in rows:
        for c in row["opciones"]:
            control = controls.setdefault(c["term"], dict(
                c, clave=common.search_key(c["term"]), capa="control_negativo",
                emparejado_con=[],
                pipeline={"stage": "02b_controles", "fecha": common.now_iso(),
                          "validado": False}))
            control["emparejado_con"].append({
                "falso_amigo": row["fa"]["term"],
                "delta_zipf": round(c["zipf"] - row["zipf"], 2),
                "delta_largo": c["largo"] - row["largo"],
                "misma_categoria": c["pos"] == row["pos"],
                "principal": row["principal"] is c,
            })
    common.write_jsonl(OUTPUT, controls.values())

    with open(PAIRINGS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["falso_amigo", "zipf", "largo", "pos", "control_principal",
                    "zipf_control", "alternativas", "motivo_sin_control"])
        for row in rows:
            p = row["principal"]
            w.writerow([row["fa"]["term"], round(row["zipf"], 2), row["largo"], row["pos"],
                        p["term"] if p else "", round(p["zipf"], 2) if p else "",
                        " ".join(c["term"] for c in row["opciones"] if c is not p),
                        row["motivo"]])

    # Zipf and length by layer: the frequency control.
    by_layer = {}
    for layer in s02.LAYERS:
        terms = [c["term"] for c in layers if c["capa_propuesta"] == layer]
        zipfs = [zipf_frequency(t, "es") for t in terms]
        by_layer[layer] = {
            "terminos": len(terms),
            "en_wordfreq": sum(z > 0 for z in zipfs),
            "zipf": summary([z for z in zipfs if z > 0]),
            "largo": summary([len(t) for t in terms]),
        }
    main_controls = [f["principal"] for f in rows if f["principal"]]
    by_layer["control_negativo (principales)"] = {
        "terminos": len(main_controls), "en_wordfreq": len(main_controls),
        "zipf": summary([c["zipf"] for c in main_controls]),
        "largo": summary([c["largo"] for c in main_controls]),
    }
    paired = [f for f in rows if f["principal"]]
    numbers = {
        "fecha": common.now_iso(),
        "parametros": cfg["controles"],
        "pool": len(pool),
        "falsos_amigos": len(rows),
        "con_control_principal": len(paired),
        "sin_control": dict(Counter(f["motivo"] for f in rows if not f["principal"])),
        "con_control_de_misma_categoria": sum(1 for f in paired
                                              if f["principal"]["pos"] == f["pos"]),
        "controles_distintos": len(controls),
        "diferencia_zipf_principal": summary([abs(f["principal"]["zipf"] - f["zipf"])
                                              for f in paired]),
        "zipf_y_largo_por_capa": by_layer,
    }
    os.makedirs(common.DATA_INTERIM, exist_ok=True)
    with open(NUMBERS, "w", encoding="utf-8") as f:
        json.dump(numbers, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: numbers[k] for k in ("pool", "falsos_amigos", "con_control_principal",
                                              "sin_control", "controles_distintos")},
                     ensure_ascii=False))
    print(f"-> {OUTPUT}")


if __name__ == "__main__":
    main()
