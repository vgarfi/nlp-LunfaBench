"""Download of the Spanish Wikcionario (extracted by wiktextract, published by
kaikki.org) and construction of a compact index by word, in the same format as
source_kaikki so the stages can use the same functions.

It adds two things the English Wiktionary lacks: classic lunfardo (tag
"Lunfardo" or raw_tag "lunfardismo" and
glosses in Spanish.

Format differences with the English Wiktionary:
- regions are capitalized tags (Chile, Andalusia, Río-de-la-Plata) and
  "ES:Argentina" categories;
- inflected forms say what they are in the gloss ("Forma del plural de
  curro."): the plural, feminine, gerund, etc. labels are derived from the
  text.

The file stays in data/raw/kaikki_es/, outside git.
"""

import gzip
import json
import os
import re

import requests

from pipeline import common

RAW_DIR = os.path.join(common.DATA_RAW, "kaikki_es")
GZ = os.path.join(RAW_DIR, "es-extract.jsonl.gz")
META = os.path.join(RAW_DIR, "descarga.json")
# v2: topics per sense and an English-loan mark (for the controls)
INDEX = os.path.join(RAW_DIR, "indice_compacto_v2.jsonl.gz")

# Gloss text of an inflected form -> label equivalent to the English
# Wiktionary ones. "Segunda persona del singular..." is a conjugation.
_FORMS = [("persona del", "first-person"), ("gerundio", "gerund"),
          ("infinitivo", "infinitive"), ("participio", "participle"),
          ("diminutivo", "diminutive"), ("aumentativo", "augmentative"),
          ("plural", "plural"), ("femenino", "feminine")]


# Spelling variants are not a link either: they are in the gloss ("Variante
# de cafiolo."). Obsolete spellings are left out: "hasta" is an obsolete
# spelling of "asta", but it is another word.
_VARIANT = re.compile(r"^(?:Variante|Grafía alternativa|Variante poco usada) de (\S+?)\.?$")
# Sense subscripts in the links: paragua₂
_SUBSCRIPTS = str.maketrans("", "", "₀₁₂₃₄₅₆₇₈₉")


def download(cfg, log=print):
    if os.path.exists(GZ):
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    url = cfg["wikcionario"]["url"]
    log(f"  downloading {url} (about 100 MB)")
    tmp = GZ + ".part"
    with requests.get(url, stream=True, timeout=cfg["http"]["timeout_segundos"],
                      headers={"User-Agent": cfg["http"]["user_agent"]}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        meta = {"url": url, "descargado": common.now_iso(),
                "last_modified": r.headers.get("Last-Modified"),
                "bytes": os.path.getsize(tmp)}
    os.replace(tmp, GZ)
    with open(META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _compact(entry):
    senses = []
    for i, s in enumerate(entry.get("senses", [])):
        tags = list(s.get("tags") or [])
        form_of = sorted({f["word"].translate(_SUBSCRIPTS) for f in s.get("form_of") or []
                          if isinstance(f, dict) and f.get("word")})
        gloss = " ".join(s.get("glosses") or [])
        if form_of:
            tags += [t for text, t in _FORMS if text in gloss.lower()]
        variant = None if form_of else _VARIANT.match(gloss.strip())
        alt_of = [variant.group(1).translate(_SUBSCRIPTS)] if variant else []
        categories = [c if isinstance(c, str) else c.get("name", "")
                      for c in s.get("categories") or []]
        senses.append({
            "id": f'wikcionario:{entry["word"]}|{entry.get("pos")}|{s.get("sense_index") or i}',
            "glosas": s.get("glosses") or [],
            "tags": tags,
            "raw_tags": s.get("raw_tags") or [],
            # Region tags (capitalized) and ES:<region> categories. ES:
            # categories can also be topical (ES:Ríos): they only count if
            # they are in the config (see prefijos_no_regionales).
            "categorias_variedad": sorted({t for t in tags if t[:1].isupper()}
                                          | {c for c in categories if c.startswith("ES:")}),
            "forma_de": form_of,
            "alt_de": alt_of,
            "temas": s.get("topics") or [],
        })
    return {"word": entry["word"], "pos": entry.get("pos"), "etimologia": None,
            "acepciones": senses,
            "prestamo_ingles": any(t.startswith("Del inglés")
                                   for t in entry.get("etymology_texts") or [])}


def _only_conjugations(entry):
    """More than 600 thousand entries are standalone conjugations (tenés,
    cabió): they add no senses or links that are used, so they are left out
    of the index."""
    senses = entry["acepciones"]
    return bool(senses) and all(a["forma_de"] and "first-person" in a["tags"]
                                for a in senses)


def index(cfg, log=print):
    """Returns {word: [compact entries]}; builds the index if it is missing."""
    # The compact index is enough: the full dump can be deleted and is only
    # downloaded again if the index is missing.
    if not os.path.exists(INDEX):
        download(cfg, log)
    if not os.path.exists(INDEX) or (os.path.exists(GZ) and
                                     os.path.getmtime(INDEX) < os.path.getmtime(GZ)):
        log("  building the compact Wikcionario index")
        tmp = INDEX + ".part"
        with gzip.open(GZ, "rt", encoding="utf-8") as f, \
                gzip.open(tmp, "wt", encoding="utf-8") as out:
            for line in f:
                e = json.loads(line)
                if e.get("lang_code") != "es":
                    continue
                compact = _compact(e)
                if not _only_conjugations(compact):
                    out.write(json.dumps(compact, ensure_ascii=False) + "\n")
        os.replace(tmp, INDEX)
    by_word = {}
    for e in common.read_jsonl(INDEX):
        by_word.setdefault(e["word"], []).append(e)
    return by_word
