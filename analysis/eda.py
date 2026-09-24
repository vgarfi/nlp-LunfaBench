"""Numbers of the exploratory analysis of the curated set: the 90 terms frozen
in data/curated/curado.jsonl, by layer. It does not depend on the
intermediate outputs of the pipeline.

Usage: python -m analysis.eda
Output: reports/eda_numeros.json (used by figure_curated.py and the report).
"""

import json
import os
import statistics
from collections import Counter

from pipeline import common

CURATED = os.path.join(common.REPO_ROOT, "data", "curated", "curado.jsonl")
MANIFEST = os.path.join(common.REPO_ROOT, "data", "curated", "manifiesto.json")
OUTPUT = os.path.join(common.REPORTS, "eda_numeros.json")
LAYERS = ["falso_amigo", "lunfardo_sin_homonimo", "polisemico_interno", "control_negativo"]
EDA_MODELS = ["robertuito", "beto", "roberta_bne"]


def subwords_in_lyrics(terms):
    """Subwords of the form that appears in fragment A (quemando, not
    quemar): that is what the model tokenizes."""
    from transformers import AutoTokenizer

    from analysis.fertility import MODELS, count_subwords
    output = {}
    for m in EDA_MODELS:
        d = MODELS[m]
        tok = AutoTokenizer.from_pretrained(d["hf"])
        output[m] = {t["id"]: count_subwords(tok, t["principal"]["forma_en_letra"], d["bpe"], d["lowercase"])
                     for t in terms}
    return output


def correlation(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5


def decade(fragment):
    year = fragment["source"].get("year") or fragment["source"].get("genius_release_year")
    return year // 10 * 10 if year else None


def main():
    terms = list(common.read_jsonl(CURATED))
    fragments = [t["principal"] for t in terms] + \
        [t["alternativo"] for t in terms if t["alternativo"]]
    lengths = [len(f["context"].replace(" / ", " ").split()) for f in fragments]

    in_lyrics = subwords_in_lyrics(terms)
    by_layer = {}
    for layer in LAYERS:
        ts = [t for t in terms if t["capa_propuesta"] == layer]
        zipfs = [t["zipf"] for t in ts if t["zipf"] > 0]
        sources = Counter(f for t in ts for f in t.get("fuentes", []))
        by_layer[layer] = {
            "terminos": len(ts),
            "zipf_mediana": round(statistics.median(zipfs), 2) if zipfs else None,
            "en_wordfreq": len(zipfs),
            "largo_mediana": statistics.median(t["largo"] for t in ts),
            # Subwords of the term (dictionary form) and of the form in the lyric.
            **{f"subwords_{m}": round(statistics.mean(t["subwords"][m] for t in ts), 2)
               for m in EDA_MODELS},
            **{f"subwords_en_letra_{m}": round(statistics.mean(in_lyrics[m][t["id"]] for t in ts), 2)
               for m in EDA_MODELS},
            "un_subword_en_los_tres": sum(1 for t in ts
                                          if all(t["subwords"][m] == 1 for m in EDA_MODELS)),
            "con_fragmento_b": sum(1 for t in ts if t["alternativo"]),
            # decade of fragment A (the primary one): Figure 1 comes from here
            "fragmentos_a_por_decada": dict(sorted(
                Counter(str(decade(t["principal"]) or "sin anio") for t in ts).items())),
            "fuentes": dict(sources),
        }

    rioplatense_terms = [t for t in terms if t["capa_propuesta"] != "control_negativo"]
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    numbers = {
        "fecha": common.now_iso(),
        "piloto_de_letras": manifest["piloto_de_letras"],
        "reemplazados_en_la_seleccion": manifest["seleccion"]["reemplazados"],
        "terminos": len(terms),
        "terminos_con_un_fragmento": sum(1 for t in terms if not t["alternativo"]),
        "a_y_b_de_la_misma_cancion": sum(
            1 for t in terms if t["alternativo"] and t["alternativo"]["source"]["genius_song_id"]
            == t["principal"]["source"]["genius_song_id"]),
        "fragmentos": len(fragments),
        # The form in the lyric is not the term's: plural, gender or conjugation.
        "fragmentos_flexionados": sum(
            1 for t in terms for f in (t["principal"], t["alternativo"])
            if f and common.search_key(f["forma_en_letra"]) != common.search_key(t["term"])),
        "fragmentos_con_otra_palabra": sum(1 for f in fragments
                                           if f.get("forma_de_otra_palabra")),
        "largo_fragmento": {"mediana": statistics.median(lengths), "min": min(lengths),
                            "max": max(lengths)},
        "canciones": len({f["source"]["genius_song_id"] for f in fragments}),
        "artistas": len({f["source"]["artist"] for f in fragments}),
        "fragmentos_a_con_anio": sum(1 for t in terms if decade(t["principal"])),
        "rango_de_decadas": [min(d for t in terms if (d := decade(t["principal"]))),
                             max(d for t in terms if (d := decade(t["principal"])))],
        # How closely the number of subwords follows frequency (average of the
        # three encoders, dictionary form).
        "correlacion_zipf_subwords": round(correlation(
            [t["zipf"] for t in terms],
            [statistics.mean(t["subwords"][m] for m in EDA_MODELS) for t in terms]), 2),
        "fuentes_de_los_75_rioplatenses": dict(Counter(f for t in rioplatense_terms
                                                       for f in t.get("fuentes", []))),
        "por_capa": by_layer,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(numbers, f, ensure_ascii=False, indent=2)
    print(json.dumps(numbers, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
