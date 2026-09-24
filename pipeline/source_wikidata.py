"""SPARQL queries to Wikidata, with a local cache and a pause between requests.

Each query is stored in data/raw/wikidata/ under the hash of its text, so a
repeated run does not query again. It uses POST because queries with long
VALUES lists do not fit in a URL.
"""

import hashlib
import json
import os
import time

import requests

from pipeline import common

CACHE_DIR = os.path.join(common.DATA_RAW, "wikidata")
_last = [0.0]


def run_query(sparql, cfg, log=print):
    """Result rows as dicts {variable: value}. Entity URI values are returned
    as QIDs (Q1486)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(sparql.encode("utf-8")).hexdigest() + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    http = cfg["http"]
    pause = max(1.0, float(http["pausa_segundos"]))
    for attempt in range(http["reintentos"]):
        wait = _last[0] + pause - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.post(cfg["wikidata"]["endpoint"], data={"query": sparql},
                              headers={"User-Agent": http["user_agent"],
                                       "Accept": "application/sparql-results+json"},
                              timeout=cfg["wikidata"]["timeout_segundos"])
        except requests.RequestException:
            r = None
        finally:
            _last[0] = time.monotonic()
        if r is not None and r.status_code == 200:
            rows = [{k: _value(v) for k, v in b.items()}
                    for b in r.json()["results"]["bindings"]]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            return rows
        log(f"  wikidata: attempt {attempt + 1} failed "
            f"({r.status_code if r is not None else 'no response'})")
        time.sleep(pause * 5 * (2 ** attempt))
    raise RuntimeError("Wikidata did not answer the query")


def _value(v):
    value = v["value"]
    if v["type"] == "uri" and value.startswith("http://www.wikidata.org/entity/"):
        return value.rsplit("/", 1)[1]
    return value


def values_block(qids):
    """List for a VALUES block: wd:Q1 wd:Q2 ..."""
    return " ".join(f"wd:{q}" for q in qids)
