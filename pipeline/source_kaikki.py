"""Download of the Spanish dictionary from kaikki.org (English Wiktionary) and
construction of a compact index by word.

The full JSONL stays in data/raw/kaikki/, outside git. The
compact index keeps only what stages 01 and 02 use: word, part of speech and,
per sense, id, glosses, labels and regional categories.
"""

import gzip
import json
import os
import re

import requests

from pipeline import common

RAW_DIR = os.path.join(common.DATA_RAW, "kaikki")
JSONL = os.path.join(RAW_DIR, "kaikki.org-dictionary-Spanish.jsonl")
META = os.path.join(RAW_DIR, "descarga.json")
INDEX = os.path.join(RAW_DIR, "indice_compacto_v3.jsonl.gz")


def download(cfg, log=print):
    if os.path.exists(JSONL):
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    url = cfg["kaikki"]["url"]
    log(f"  downloading {url} (about 1 GB)")
    tmp = JSONL + ".part"
    with requests.get(url, stream=True, timeout=cfg["http"]["timeout_segundos"],
                      headers={"User-Agent": cfg["http"]["user_agent"]}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        meta = {"url": url, "descargado": common.now_iso(),
                "last_modified": r.headers.get("Last-Modified"),
                "bytes": os.path.getsize(tmp)}
    os.replace(tmp, JSONL)
    with open(META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _compact(entry):
    senses = []
    for i, s in enumerate(entry.get("senses", [])):
        senses.append({
            "id": s.get("id") or f'{entry["word"]}|{entry.get("pos")}|{i}',
            "glosas": s.get("glosses") or s.get("raw_glosses") or [],
            "tags": s.get("tags", []),
            "raw_tags": s.get("raw_tags", []),
            # Categories such as "Rioplatense Spanish" or "Peninsular Spanish":
            # another regional signal, inspected in stage 02.
            "categorias_variedad": sorted({c["name"] for c in s.get("categories", [])
                                           if isinstance(c, dict)
                                           and c.get("name", "").endswith(" Spanish")}),
            # "curros": plural of curro. List of lemmas; empty if not an inflection.
            "forma_de": sorted({f["word"] for f in s.get("form_of", [])
                                if isinstance(f, dict) and f.get("word")}),
            "alt_de": sorted({f["word"] for f in s.get("alt_of", [])
                              if isinstance(f, dict) and f.get("word")}),
            "temas": s.get("topics") or [],
        })
    return {"word": entry["word"], "pos": entry.get("pos"),
            "etimologia": entry.get("etymology_number"), "acepciones": senses,
            "prestamo_ingles": bool(re.search(r"(?i)borrow(ed|ing) from English",
                                              entry.get("etymology_text") or ""))}


def index(cfg, log=print):
    """Returns {word: [compact entries]}; builds the index if it is missing."""
    # The compact index is enough: the full dump can be deleted and is only
    # downloaded again if the index is missing.
    if not os.path.exists(INDEX):
        download(cfg, log)
    if not os.path.exists(INDEX) or (os.path.exists(JSONL) and
                                     os.path.getmtime(INDEX) < os.path.getmtime(JSONL)):
        log("  building the compact kaikki index")
        tmp = INDEX + ".part"
        with open(JSONL, encoding="utf-8") as f, gzip.open(tmp, "wt", encoding="utf-8") as out:
            for line in f:
                e = json.loads(line)
                if e.get("lang_code") not in (None, "es"):
                    continue
                out.write(json.dumps(_compact(e), ensure_ascii=False) + "\n")
        os.replace(tmp, INDEX)
    by_word = {}
    for e in common.read_jsonl(INDEX):
        by_word.setdefault(e["word"], []).append(e)
    return by_word
