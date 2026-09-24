"""Stage 01: candidates.

Gathers three branches and keeps their union:
- terms of diccionarioargentino.com whose best definition reaches the
  minimum score (votes);
- kaikki lemmas (English Wiktionary) with some sense marked for the target
  variety;
- lemmas of the Spanish Wikcionario with some sense marked for the target
  variety or as lunfardo (it covers the tango lunfardo that the collaborative
  dictionary, with contributions from 2014 to 2025, lacks).
Plurals, spelling variants and gerunds are merged into their lemma; gender
pairs stay separate (see link_variants).
The same simple rules apply to the three: out go acronyms, entries with
numbers or symbols, expressions of more than max_palabras words and memes.

Outputs:
- data/interim/candidatos.jsonl: one candidate per line, with provenance.
- data/interim/candidatos_descartados.csv: what did not pass and why.
- data/raw/diccionario_argentino/definiciones.jsonl: every parsed definition
  (outside git: it is a copy of the site).
- data/interim/01_candidatos_numeros.json: funnel numbers (used by freeze).

Usage:
    python -m pipeline.stage01_candidates               # everything
    python -m pipeline.stage01_candidates --letters c   # test with one letter
    python -m pipeline.stage01_candidates --cache-only  # only dictionary pages already in data/raw/
"""

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict

from wordfreq import zipf_frequency

from pipeline import common, regions
from pipeline import source_diccionario_argentino as da
from pipeline import source_kaikki as kk
from pipeline import source_wikcionario as wk

# Lexical sources: name, module and block of regional marks in the config.
LEXICAL_SOURCES = [("kaikki", kk, "variedades"),
                   ("wikcionario", wk, "variedades_wikcionario")]

OUTPUT = os.path.join(common.DATA_INTERIM, "candidatos.jsonl")
DISCARDED = os.path.join(common.DATA_INTERIM, "candidatos_descartados.csv")
VARIANTS = os.path.join(common.DATA_INTERIM, "variantes_fusionadas.csv")
GENDER_PAIRS = os.path.join(common.DATA_INTERIM, "pares_de_genero.csv")
DEFINITIONS = os.path.join(da.RAW_DIR, "definiciones.jsonl")
NUMBERS = os.path.join(common.DATA_INTERIM, "01_candidatos_numeros.json")

# Order in which the rules are applied (it defines the funnel).
RULES = ["sigla", "numeros_o_simbolos", "varias_palabras", "meme", "nombre_propio"]

_EDGE_PUNCTUATION = "¡!¿?.,;:\"«»“”()[]{}*"


def lemma_forms(lemma):
    lemma = common.normalize_homoglyphs(lemma)
    # gender mark: chabón/a, falluto/a, pibe(a)
    lemma = re.sub(r"\s*(/|\()\s*(a|o|as|os)\)?(?=$|[,;/\s])", "", lemma, flags=re.I)
    # clarifications in parentheses, even unclosed ones: "churro (no la factura"
    lemma = re.sub(r"\s*\(.*$", "", lemma)
    forms = []
    # variants: "culiado/culiao/culiau", "chetardo, chetardi"
    for part in re.split(r"[,;/]", lemma):
        part = re.sub(r"\s+", " ", part).strip().strip(_EDGE_PUNCTUATION).strip()
        if part:
            forms.append(part)
    return forms


def is_acronym(original):
    """C.D.P, CDT, CFK."""
    if re.fullmatch(r"(\w\.)+\w?\.?", original):
        return True
    letters = [c for c in original if c.isalpha()]
    no_vowels = not any(c.lower() in "aeiouáéíóú" for c in letters)
    return len(letters) >= 2 and all(c.isupper() for c in letters) and \
        (len(letters) <= 4 or no_vowels)


def evaluate_rules(term, originals, lexical_pos, max_words):
    """Reasons to discard a candidate, in the order of RULES."""
    reasons = []
    if originals and sum(is_acronym(o) for o in originals) > len(originals) / 2:
        reasons.append("sigla")
    if re.search(r"\d", term) or re.search(r"[^\w\s'\-]", term) or "_" in term:
        reasons.append("numeros_o_simbolos")
    if len(term.split()) > max_words:
        reasons.append("varias_palabras")
    tokens = re.split(r"[\s\-]+", term)
    if any(len(t) == 1 and t not in "aeouy" for t in tokens) or re.search(r"(\w)\1\1", term):
        reasons.append("meme")
    # Proper name: the lexical sources only know it as a name, or every
    # spelling in the dictionary is several capitalized words.
    if (lexical_pos and set(lexical_pos) == {"name"}) or (
            originals and all(len(o.split()) > 1 and all(t[:1].isupper() for t in o.split())
                               for o in originals)):
        reasons.append("nombre_propio")
    return reasons


def group_dictionary(entries):
    """Unique definitions (by id) grouped by accent-free key. The site
    searches ignoring case and accents, so the same definition can show up
    on several pages."""
    seen = {}
    for e in entries:
        for d in e["definiciones"]:
            def_key = d["id_definicion"] or (d["url"], d["numero"])
            seen.setdefault(def_key, dict(d, titulo_indice=e["titulo"]))
    groups = defaultdict(list)
    for d in seen.values():
        forms = lemma_forms(d["lema"] or d["titulo_indice"])
        if not forms:
            continue
        d["formas"] = forms
        groups[common.search_key(forms[0])].append(d)
    return list(seen.values()), groups


def index_source(index, varieties, excluded_pos):
    """For a lexical source (kaikki or Wikcionario): words by exact form and
    by accent-free key, and lemmas with some target sense."""
    exact, no_accent = defaultdict(set), defaultdict(set)
    with_target = {}
    for word, entries in index.items():
        exact[common.normalize(word)].add(word)
        no_accent[common.search_key(word)].add(word)
        senses = []
        for e in entries:
            if e["pos"] in excluded_pos:
                continue
            for a in e["acepciones"]:
                region, marks = regions.sense_region(a, varieties)
                if a["forma_de"] or region != "objetivo":
                    continue
                senses.append({"id": a["id"], "pos": e["pos"], "glosas": a["glosas"],
                               "marcas": marks})
        if senses:
            with_target[word] = senses
    return exact, no_accent, with_target


# Priority when a form points to several candidate lemmas: chapas is the
# plural of chapa and also a conjugation of chapar; the plural wins.
_PRIORITY = ["plural", "variante_grafica", "gerundio", "diminutivo", "regla_plural"]
_VERBAL = {"first-person", "second-person", "third-person", "participle", "infinitive",
           "indicative", "subjunctive", "imperative"}


def form_type(tags, form, lemma):
    """What kind of 'form of' it is: plural, gerund, diminutive or feminine
    (form and lemma are accent-free keys). Personal conjugations,
    participles and infinitives with a pronoun return None: they are often
    another word (chape = kiss, choreo = theft, cebarse is not cebar).
    Plural is only a change of number: chetas is the plural of cheta, but as
    a form of cheto it is a feminine and stays as a gender pair."""
    tags = set(tags)
    if tags & {"diminutive", "augmentative", "superlative"}:
        return "diminutivo"
    if "gerund" in tags:
        return "gerundio"
    if tags & _VERBAL:
        return None
    if form in (lemma + "s", lemma + "es") or ("plural" in tags and "feminine" not in tags):
        return "plural"
    if "feminine" in tags:
        return "femenino"
    return None


def share_or_undefined(defs_x, defs_y, cfg):
    """Veto of the collaborative dictionary: if both words have definitions
    there, some of them have to talk about the same thing."""
    if not defs_x or not defs_y:
        return True
    return common.share_meaning([d["texto"] or "" for d in defs_x],
                                [d["texto"] or "" for d in defs_y],
                                cfg["etapa01_candidatos"]["similitud_definiciones"])


def repeats_senses(variant_entries, lemma_entries, threshold):
    """A spelling variant is merged if it has no senses of its own or if
    the ones it has repeat the lemma's (kaikki repeats chamuyar's senses in
    chamullar). If most are different, it is another word: cacho = piece,
    even if another entry lists it as a variant of gacho."""
    own = [a["glosas"] for e in variant_entries for a in e["acepciones"]
           if not a["forma_de"] and not a["alt_de"]]
    if not own:
        return True
    of_lemma = [a["glosas"] for e in lemma_entries for a in e["acepciones"]
                if not a["forma_de"] and not a["alt_de"]]
    repeated = sum(any(common.same_gloss(g, l, threshold) for l in of_lemma) for g in own)
    return repeated / len(own) >= 0.5


def link_variants(keys, data_of, sources, cfg):
    """Returns:
    - variant_of {key: (lemma_key, rule)}: plurals, spelling variants and
      gerunds of another candidate, which are merged into the lemma (curros
      -> curro, chamullar -> chamuyar);
    - gender_pairs {(feminine_key, masculine_key)}: feminines of another
      candidate, which are NOT merged because in lunfardo they are sometimes
      another word (pucha is not the feminine of pucho) and sometimes not
      (cheta and cheto). They stay separate and marked.

    It only merges into a lemma that is also a candidate, so a lexicalized
    form (cabió) does not turn into a general verb (caber). And only if no
    source gives the form senses of its own that matter: chauchas (little
    money) is not just the plural of chaucha (pod). A sense of its own does
    not matter if it is from another region.

    Last filter for spelling variants: if both words have definitions in the
    collaborative dictionary and they share no meaning, they are not merged.
    In Spain facho is a variant of facha, but here facho is fascist and facha
    is looks; pebete is a sandwich, not a variant of pibe. It is not applied
    to plurals: the definitions are short free text, and azules (police,
    cana, yuta) shares no words with azul (a way to call the police) even
    though they are the same."""
    ecfg = cfg["etapa01_candidatos"]
    excluded_pos = set(ecfg["pos_excluidas"])
    gloss_threshold = cfg["etapa02_capa"]["similitud_glosa"]
    chosen, links, pairs = [], {}, set()
    # Sorted: the order of a set changes between runs, and with it the lemma
    # of some groups changed (cafisho or fiolo).
    for x in sorted(keys):
        options = []
        defs_x, _, _, by_source = data_of(x)
        entries = [(f, w, e) for name, f in sources.items()
                   for w in by_source[name]["palabras"]
                   for e in f["indice"].get(w, []) if e["pos"] not in excluded_pos]
        own_matter = any(
            regions.sense_region(a, f["variedades"])[0] != "otra"
            for f, _, e in entries for a in e["acepciones"]
            if not a["forma_de"] and not a["alt_de"])
        for f, w, e in entries:
            for a in e["acepciones"]:
                linked = [(common.search_key(l), form_type(a["tags"], x, common.search_key(l)))
                          for l in a["forma_de"]]
                # A spelling variant is the same word, unless it is from
                # another region (chino is "china" = pebble only in Andalusia)
                # or it has senses of its own different from the lemma's
                # (cacho = piece, even if it is also a variant of gacho).
                if regions.sense_region(a, f["variedades"])[0] in \
                        ("objetivo", "amplia", "general"):
                    linked += [(common.search_key(l), "variante_grafica")
                               for l in a["alt_de"]
                               if repeats_senses(f["indice"].get(w, []),
                                                 f["indice"].get(l, []), gloss_threshold)]
                for y, rule in linked:
                    # Never into a longer expression: villa is not a form of
                    # villa miseria.
                    if y == x or y not in keys or rule is None or \
                            len(y.split()) > len(x.split()):
                        continue
                    if rule == "variante_grafica" and \
                            not share_or_undefined(defs_x, data_of(y)[0], cfg):
                        continue
                    if rule == "femenino":
                        pairs.add((x, y))
                    elif rule == "diminutivo" and not ecfg["fusionar_diminutivos"]:
                        continue
                    elif rule == "variante_grafica" or not own_matter:
                        options.append((_PRIORITY.index(rule), y, rule))
        if not entries and " " not in x:
            # No lexical sources: plural by a simple rule; gender is only
            # marked. Single words only: "a las chapas" is not a plural.
            for suffix in ("es", "s"):
                y = x[:-len(suffix)] if x.endswith(suffix) else None
                if y and len(y) >= 3 and y in keys:
                    options.append((_PRIORITY.index("regla_plural"), y, "regla_plural"))
                    break
            for suffix, replacement in (("a", "o"), ("as", "os")):
                y = x[:-len(suffix)] + replacement if x.endswith(suffix) else None
                if y and y in keys:
                    pairs.add((x, y))
        if options:
            _, y, rule = min(options)
            chosen.append((x, y, rule))

    # Between two spelling variants, the lemma is the one used most here, even
    # if Wikcionario takes the normative one as lemma: sudestada and not
    # surestada, tero and not teruteru.
    def evidence(k):
        defs, _, forms, by_source = data_of(k)
        frequency = max(zipf_frequency(f, "es") for f in set(forms) | {k})
        return (bool(defs), any(pf["objetivo"] for pf in by_source.values()), frequency)

    for x, y, rule in chosen:
        if rule == "variante_grafica" and evidence(x) > evidence(y) and \
                len(x.split()) <= len(y.split()) and not any(v == y for v, _, _ in chosen):
            links[y] = (x, "variante_grafica_invertida")
        else:
            links.setdefault(x, (y, rule))

    def root(x):
        trail = []
        while x in links and x not in trail:
            trail.append(x)
            x = links[x][0]
        return x

    variant_of = {x: (root(x), rule) for x, (_, rule) in links.items() if root(x) != x}
    # Pairs are expressed between lemmas (chetas is already cheta).
    gender_pairs = set()
    for fem, masc in pairs:
        fem, masc = root(fem), root(masc)
        if fem != masc:
            gender_pairs.add((fem, masc))
    return variant_of, gender_pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--letters", help="only these letters of the index (for testing)")
    ap.add_argument("--cache-only", action="store_true",
                    help="do not download new dictionary pages")
    args = ap.parse_args()

    cfg = common.load_config()
    ecfg = cfg["etapa01_candidatos"]
    excluded_pos = set(ecfg["pos_excluidas"])

    print("diccionarioargentino.com")
    entries, client = da.download(cfg, letters=args.letters, cache_only=args.cache_only)
    definitions, groups = group_dictionary(entries)
    common.write_jsonl(DEFINITIONS, definitions)

    sources = {}
    for name, module, cfg_key in LEXICAL_SOURCES:
        print(name)
        index = module.index(cfg)
        exact, no_accent, with_target = index_source(index, cfg[cfg_key], excluded_pos)
        if args.letters:  # in a test, compare only against the same letters
            with_target = {p: a for p, a in with_target.items()
                           if common.search_key(p)[:1] in args.letters}
        target_by_key = defaultdict(list)
        for p in with_target:
            target_by_key[common.search_key(p)].append(p)
        sources[name] = {"indice": index, "variedades": cfg[cfg_key], "exacta": exact,
                         "sin_tilde": no_accent, "con_objetivo": with_target,
                         "objetivo_por_clave": target_by_key}

    keys = set(groups) | {k for f in sources.values() for k in f["objetivo_por_clave"]}

    def key_data(key):
        defs = groups.get(key, [])
        originals = [d["formas"][0] for d in defs] or sorted(
            {p for f in sources.values() for p in f["objetivo_por_clave"].get(key, [])})
        forms = Counter(common.normalize(o) for o in originals)
        by_source = {}
        for name, f in sources.items():
            # Match: exact first, accent-free as a fallback.
            words = set().union(*(f["exacta"].get(x, set()) for x in forms))
            match = "exacta" if words else None
            if not words:
                words = set(f["sin_tilde"].get(key, set()))
                match = "sin_tildes" if words else None
            by_source[name] = {
                "palabras": words, "coincidencia": match,
                "objetivo": {p: f["con_objetivo"][p] for p in words if p in f["con_objetivo"]}}
        return defs, originals, forms, by_source

    variant_of, gender_pairs = link_variants(
        keys, key_data, sources, cfg) \
        if ecfg["fusionar_variantes"] else ({}, set())
    variants_of = defaultdict(list)
    for v, (lemma, rule) in variant_of.items():
        variants_of[lemma].append((v, rule))
    gender_pair = defaultdict(list)
    for fem, masc in gender_pairs:
        gender_pair[fem].append(masc)
        gender_pair[masc].append(fem)

    candidates, discarded = [], []
    for key in sorted(keys - set(variant_of)):
        defs, originals, forms, by_source = key_data(key)
        lexical_pos = sorted({e["pos"] for name, f in sources.items()
                              for p in by_source[name]["palabras"]
                              for e in f["indice"].get(p, [])})
        # Variants add their definitions and target senses to the lemma.
        # Their words do not go into "palabras": copada is also a bird, and
        # that is not a sense of copado.
        variants = []
        all_defs = list(defs)
        all_targets = {n: dict(pf["objetivo"]) for n, pf in by_source.items()}
        for v, rule in sorted(variants_of.get(key, [])):
            v_defs, _, v_forms, v_by_source = key_data(v)
            all_defs += v_defs
            for n in all_targets:
                all_targets[n].update(v_by_source[n]["objetivo"])
            variants.append({"clave": v, "regla": rule, "formas": dict(v_forms),
                             "n_definiciones": len(v_defs),
                             **{f"palabras_{n}": sorted(v_by_source[n]["palabras"])
                                for n in sources}})

        # Spelling of the term: the one of a lexical source if it matches a
        # single word (recovers accents the contribution lost), otherwise the
        # most used one in the collaborative dictionary.
        term = spelling_source = None
        for name in sources:
            pf = by_source[name]
            preferred = set(pf["objetivo"]) or pf["palabras"]
            if len({common.normalize(p) for p in preferred}) == 1:
                term, spelling_source = common.normalize(next(iter(preferred))), name
                break
        if term is None:
            term, spelling_source = forms.most_common(1)[0][0], \
                "diccionario_argentino" if defs else "objetivo"

        max_score = max((d["puntaje"] for d in all_defs if d["puntaje"] is not None),
                        default=None)
        reasons = evaluate_rules(term, originals, lexical_pos, ecfg["max_palabras"])
        marks = []
        if "nombre_propio" in reasons and not ecfg["descartar_nombres_propios"]:
            reasons.remove("nombre_propio")
            marks.append("posible_nombre_propio")
        branches = {"diccionario": bool(all_defs) and max_score is not None
                    and max_score >= ecfg["puntaje_minimo"],
                    **{n: bool(all_targets[n]) for n in sources}}
        if not any(branches.values()):
            reasons.insert(0, "puntaje_bajo" if all_defs else "sin_definiciones")

        cand = {
            "term": term,
            "clave": key,
            "origen_grafia": spelling_source,
            "formas": dict(forms),
            "n_palabras": len(term.split()),
            "fuentes": (["diccionario_argentino"] if all_defs else [])
            + [n for n in sources if branches[n]],
            "variantes": variants,
            # the other member of a cheto/cheta pair: they are not merged
            "par_de_genero": sorted(gender_pair.get(key, [])),
            "diccionario_argentino": None if not all_defs else {
                "urls": sorted({d["url"] for d in all_defs}),
                "puntaje_max": max_score,
                "n_definiciones": len(all_defs),
                "definiciones": sorted(
                    [{k: d[k] for k in ("id_definicion", "numero", "lema", "puntaje", "texto",
                                        "ejemplos", "autor", "antiguedad", "anio_aprox", "url")}
                     for d in all_defs], key=lambda d: -(d["puntaje"] or 0)),
            },
            **{n: {
                "coincidencia": by_source[n]["coincidencia"],
                "palabras": sorted(by_source[n]["palabras"]),
                "pos": sorted({e["pos"] for p in by_source[n]["palabras"]
                               for e in sources[n]["indice"].get(p, [])}),
                "acepciones_objetivo": [dict(a, palabra=p) for p in sorted(all_targets[n])
                                        for a in all_targets[n][p]],
            } for n in sources},
            "ramas": branches,
            "marcas": marks,
            "pipeline": {"stage": "01_candidatos", "fecha": common.now_iso(), "validado": False},
        }
        if reasons:
            discarded.append((cand, reasons))
        else:
            candidates.append(cand)

    common.write_jsonl(OUTPUT, candidates)
    with open(DISCARDED, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["term", "fuentes", "motivos", "puntaje_max", "pos", "url"])
        for c, reasons in discarded:
            dic = c["diccionario_argentino"] or {}
            pos = sorted({p for n in sources for p in c[n]["pos"]})
            w.writerow([c["term"], "+".join(c["fuentes"]), "+".join(reasons),
                        dic.get("puntaje_max"), "+".join(pos), (dic.get("urls") or [""])[0]])

    with open(VARIANTS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variante", "lema", "regla"])
        for v, (lemma, rule) in sorted(variant_of.items()):
            w.writerow([v, lemma, rule])

    by_key = {c["clave"]: c for c in candidates}
    with open(GENDER_PAIRS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["femenino", "masculino", "def_femenino", "def_masculino"])
        for fem, masc in sorted(gender_pairs):
            if fem in by_key and masc in by_key:
                w.writerow([by_key[fem]["term"], by_key[masc]["term"],
                            definition_summary(by_key[fem]),
                            definition_summary(by_key[masc])])

    numbers = summarize(args, cfg, entries, client, definitions, groups, sources,
                        candidates, discarded, variant_of)
    os.makedirs(common.DATA_INTERIM, exist_ok=True)
    with open(NUMBERS, "w", encoding="utf-8") as f:
        json.dump(numbers, f, ensure_ascii=False, indent=2)
    print(json.dumps(numbers["embudo"], ensure_ascii=False, indent=2))
    print(f"candidates: {len(candidates)} -> {OUTPUT}")


def definition_summary(cand):
    """The rioplatense sense in one line: from the collaborative dictionary,
    else from Wikcionario (Spanish), else from kaikki (English)."""
    dic = cand["diccionario_argentino"]
    if dic and dic["definiciones"]:
        return dic["definiciones"][0]["texto"][:120]
    for name in ("wikcionario", "kaikki"):
        target_senses = cand[name]["acepciones_objetivo"]
        if target_senses:
            return f"({name}) " + "; ".join(target_senses[0]["glosas"])[:110]
    return ""


def summarize(args, cfg, entries, client, definitions, groups, sources,
              candidates, discarded, variant_of):
    all_rows = [(c, []) for c in candidates] + discarded
    scores = sorted(max((d["puntaje"] or 0) for d in defs) for defs in groups.values())

    def quantile(q):
        return scores[min(len(scores) - 1, int(q * len(scores)))] if scores else None

    def funnel(branch, branch_filter, begin):
        alive = [(c, m) for c, m in all_rows if branch_filter(c)]
        steps = [begin, ["sin variantes flexivas", len(alive)]]
        if branch == "diccionario":
            alive = [(c, m) for c, m in alive
                     if (c["diccionario_argentino"]["puntaje_max"] or 0)
                     >= cfg["etapa01_candidatos"]["puntaje_minimo"]]
            steps.append([f'puntaje >= {cfg["etapa01_candidatos"]["puntaje_minimo"]}', len(alive)])
        for rule in RULES:
            if rule == "nombre_propio" and not cfg["etapa01_candidatos"]["descartar_nombres_propios"]:
                continue
            alive = [(c, m) for c, m in alive if rule not in m]
            steps.append([f"sin {rule}", len(alive)])
        return steps

    combinations = Counter("+".join(c["fuentes"]) for c in candidates)
    return {
        "fecha": common.now_iso(),
        "letras": args.letters or cfg["diccionario_argentino"]["letras"],
        "parametros": {"variedades": cfg["variedades"],
                       "variedades_wikcionario": cfg["variedades_wikcionario"],
                       **cfg["etapa01_candidatos"]},
        "diccionario": {
            "entradas_indice": len(entries),
            "paginas_sin_bajar": sum(not e["descargada"] for e in entries),
            "paginas_bajadas_en_esta_corrida": client.downloads,
            "definiciones_unicas": len(definitions),
            "terminos_unicos": len(groups),
            "puntaje_max_por_termino": {"p25": quantile(.25), "mediana": quantile(.5),
                                        "p75": quantile(.75), "p90": quantile(.9),
                                        "max": scores[-1] if scores else None},
        },
        **{n: {"lemas_con_acepcion_objetivo": len(f["con_objetivo"])}
           for n, f in sources.items()},
        "variantes_fusionadas": {"total": len(variant_of),
                                 "por_regla": dict(Counter(r for _, r in variant_of.values()))},
        "candidatos_con_par_de_genero_pendiente": sum(1 for c in candidates if c["par_de_genero"]),
        "embudo": {
            "diccionario": funnel("diccionario", lambda c: c["diccionario_argentino"] is not None,
                                  ["terminos unicos", len(groups)]),
            **{n: funnel(n, lambda c, n=n: c["ramas"][n],
                         ["lemas con acepcion objetivo", len(f["con_objetivo"])])
               for n, f in sources.items()},
            "union": {"candidatos": len(candidates), "por_fuente": dict(combinations)},
        },
        "motivos_descarte": dict(Counter(m for _, ms in discarded for m in ms)),
        "marcas": dict(Counter(m for c in candidates for m in c["marcas"])),
        "sensibilidad": {
            # How many dictionary terms would pass with another vote threshold
            # (before the rules), and how many final candidates have 1 or 2
            # words, to decide puntaje_minimo and max_palabras.
            "terminos_diccionario_por_puntaje_minimo": {
                str(u): sum(1 for defs in groups.values()
                            if max((d["puntaje"] or 0) for d in defs) >= u)
                for u in (-1000, 0, 1, 3, 5, 10)},
            "candidatos_por_n_palabras": dict(Counter(c["n_palabras"] for c in candidates)),
        },
    }


if __name__ == "__main__":
    main()
