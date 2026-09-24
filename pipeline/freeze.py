"""Freezes the corpus of the curated set in data/curated/.

Leaves a self-contained copy of the 90 chosen terms (stage 04), with all their
provenance, so using the benchmark does not depend on the intermediate
outputs or on the downloads. Regenerating this same corpus does need the
downloads in data/raw/ (see the README).

Outputs in data/curated/:
- curado.jsonl: one term per line, with the proposed layer and its reason,
  the definitions of the collaborative dictionary (with URL), the Wiktionary
  and Wikcionario senses that decided the layer (with their IDs), fragments A
  and B with their song, artist, origin and year, the Zipf, the fertility and,
  for the controls, the false friends they are paired with.
- config.yaml: copy of the configuration used to build it.
- manifiesto.json: date, version of each source, funnel numbers, seeds and
  the SHA-256 hash of each file.

Usage: python -m pipeline.freeze
"""

import csv
import hashlib
import json
import os
import shutil

from wordfreq import zipf_frequency

from pipeline import common
from pipeline import stage01_candidates as s01
from pipeline import stage02_layer as s02
from pipeline import stage02b_controls as s02b
from pipeline import stage04_curated as s04

CURATED_DIR = os.path.join(common.REPO_ROOT, "data", "curated")
CURATED = os.path.join(CURATED_DIR, "curado.jsonl")
MANIFEST = os.path.join(CURATED_DIR, "manifiesto.json")
FERTILITY = os.path.join(common.DATA_INTERIM, "fertilidad_por_termino.csv")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_TOKENIZERS = {}


def subwords(term):
    from transformers import AutoTokenizer

    from analysis.fertility import MODELS, count_subwords
    if not _TOKENIZERS:
        _TOKENIZERS.update({m: AutoTokenizer.from_pretrained(d["hf"]) for m, d in MODELS.items()})
    return {m: count_subwords(_TOKENIZERS[m], term, d["bpe"], d["lowercase"]) for m, d in MODELS.items()}


def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg = common.load_config()
    pre = list(common.read_jsonl(s04.SELECTION))
    layers = {c["clave"]: c for c in common.read_jsonl(s02.OUTPUT)}
    candidates = {c["clave"]: c for c in common.read_jsonl(s01.OUTPUT)}
    controls = {c["clave"]: c for c in common.read_jsonl(s02b.OUTPUT)}
    with open(FERTILITY, encoding="utf-8") as f:
        fertility = {(r["term"], r["capa"]): {k: int(v) for k, v in r.items()
                                              if k not in ("term", "capa")}
                     for r in csv.DictReader(f)}

    rows = []
    for p in pre:
        kind, key = p["objetivo"].split(":", 1)
        row = {k: p[k] for k in ("id", "objetivo", "term", "capa_propuesta",
                                 "acepcion_de_referencia", "fuente_acepcion",
                                 "principal", "alternativo")}
        row["zipf"] = zipf_frequency(p["term"], "es")
        row["largo"] = len(p["term"])
        # Fertility was measured for the main controls; the curated set can
        # have other controls from the pairing: those are measured here.
        row["subwords"] = fertility.get((p["term"], p["capa_propuesta"])) or \
            subwords(p["term"])
        if kind == "cand":
            c, layer = candidates[key], layers[key]
            row.update({
                "motivo_capa": layer["motivo"],
                "marcas": layer["marcas"],
                "fuentes": c["fuentes"],
                "formas": c["formas"],
                "variantes": [v["clave"] for v in c["variantes"]],
                "diccionario_argentino": c["diccionario_argentino"],
                "acepciones_kaikki": layer["acepciones_kaikki"],
                "acepciones_wikcionario": layer["acepciones_wikcionario"],
            })
        else:
            c = controls[key]
            row.update({
                "motivo_capa": "control: espanol general emparejado en frecuencia y largo",
                "glosa_general": c["glosa"], "fuente_glosa": c["fuente_glosa"],
                "ids_acepciones": c["ids_acepciones"],
                "emparejado_con": c["emparejado_con"],
            })
        rows.append(row)

    os.makedirs(CURATED_DIR, exist_ok=True)
    common.write_jsonl(CURATED, rows)
    shutil.copy(os.path.join(common.REPO_ROOT, "config.yaml"),
                os.path.join(CURATED_DIR, "config.yaml"))

    raw = common.DATA_RAW
    numbers = {n: read_json(os.path.join(common.DATA_INTERIM, n)) for n in (
        "01_candidatos_numeros.json", "02_capa_numeros.json", "02b_controles_numeros.json",
        "03a_artistas_numeros.json", "03b_contextos_numeros.json",
        "04_seleccion_numeros.json")}
    n01, n02 = numbers["01_candidatos_numeros.json"], numbers["02_capa_numeros.json"]
    manifest = {
        "congelado": common.now_iso(),
        "descripcion": "Los 90 terminos del conjunto curado (etapa 04), sorteados por capa con "
                       "semilla entre los que tienen fragmentos de letra. Las etapas 01 a 02b "
                       "corrieron completas; la 03b es una muestra piloto.",
        "fuentes": {
            "diccionarioargentino.com": {
                "descargado": "2026-09-23", "paginas": 3525,
                "definiciones": numbers["01_candidatos_numeros.json"]["diccionario"][
                    "definiciones_unicas"]},
            "kaikki (Wiktionary en ingles)": read_json(os.path.join(raw, "kaikki", "descarga.json")),
            "Wikcionario (kaikki es-extract)": read_json(os.path.join(raw, "kaikki_es",
                                                                      "descarga.json")),
            "wikidata": {"consultado": "2026-09-23/24",
                         "endpoint": cfg["wikidata"]["endpoint"]},
            "musicbrainz": {"consultado": "2026-09-23/24"},
            "genius": {"consultado": "2026-09-24",
                       "nota": "solo metadatos en cache; las letras no se guardan"},
            "wordfreq": {"lista": "es, best"},
        },
        "semillas": {"piloto_de_artistas": cfg["etapa03b_contextos"]["semilla"],
                     "seleccion": cfg["etapa04_curado"]["semilla"]},
        "cuotas_del_curado": cfg["etapa04_curado"]["cuotas"],
        "terminos": len(rows),
        # Where the 90 come from: numbers of the stages that ran in full.
        "embudo": {
            "diccionario_terminos": n01["diccionario"]["terminos_unicos"],
            "diccionario_definiciones": n01["diccionario"]["definiciones_unicas"],
            "kaikki_lemas_objetivo": n01["kaikki"]["lemas_con_acepcion_objetivo"],
            "wikcionario_lemas_objetivo": n01["wikcionario"]["lemas_con_acepcion_objetivo"],
            "candidatos_etapa01": n02["candidatos"],
            "por_capa_etapa02": n02["por_capa"],
            "controles_emparejados": numbers["02b_controles_numeros.json"]["con_control_principal"],
        },
        "piloto_de_letras": {
            "artistas": numbers["03b_contextos_numeros.json"]["canciones"]["artistas_con_canciones"],
            "canciones": numbers["03b_contextos_numeros.json"]["letras"]["canciones_procesadas"],
            "descartadas_por_idioma": sum(
                numbers["03b_contextos_numeros.json"]["letras"]["descartadas"].values()),
            # Where the terms were searched.
            "canciones_en_espanol": numbers["03b_contextos_numeros.json"]["letras"][
                "canciones_en_espanol"],
            "artistas_en_espanol": numbers["03b_contextos_numeros.json"]["letras"][
                "artistas_en_espanol"],
        },
        "seleccion": numbers["04_seleccion_numeros.json"],
        "archivos": {},
    }
    for name in ("curado.jsonl", "config.yaml"):
        manifest["archivos"][name] = sha256(os.path.join(CURATED_DIR, name))
    for path in (s04.SHEET, s04.KEY_FILE):
        manifest["archivos"][os.path.relpath(path, common.REPO_ROOT)] = sha256(path)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"{len(rows)} terms -> {CURATED_DIR}")


if __name__ == "__main__":
    main()
