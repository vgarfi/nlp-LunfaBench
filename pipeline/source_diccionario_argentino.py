"""Download and parsing of diccionarioargentino.com.

The site requires attribution and a link: each definition keeps the URL of
its page and its id. Pages are requested one at a time, with a minimum pause of 1 s and a local cache in
data/raw/diccionario_argentino/.

Site structure:
- /terms/<letter>: alphabetical index, a single page per letter.
- /term/<term>: numbered definitions, each with a score (votes), text,
  examples, author and age of the contribution.
"""

import os
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from pipeline import common

RAW_DIR = os.path.join(common.DATA_RAW, "diccionario_argentino")
CACHE_DIR = os.path.join(RAW_DIR, "cache")

_UNITS = {"second": 0, "minute": 0, "hour": 0, "day": 0, "week": 0,
          "month": 1 / 12, "year": 1}


def parse_index(html):
    """List of (title, url) of an alphabetical index. Ignores the side column
    of random terms, which changes on every visit."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for li in soup.select("ul.terms li:not(.title)"):
        a = li.find("a", href=True)
        if a and "/term/" in a["href"]:
            entries.append((a.get_text(strip=True), a["href"].strip()))
    return entries


def approx_year(age, download_date):
    """'7 years ago' -> approximate year of the contribution, relative to the
    download."""
    m = re.search(r"(\d+|an?)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
                  age or "")
    if not m:
        return None
    n = 1 if m.group(1) in ("a", "an") else int(m.group(1))
    return round(download_date.year - n * _UNITS[m.group(2)])


def parse_term(html, url, download_date):
    """Definitions of a /term/ page. Each one keeps the form written by its
    contributor (with or without accents)."""
    soup = BeautifulSoup(html, "html.parser")
    definitions = []
    for panel in soup.select("div.panel.panel-default"):
        title = panel.select_one(".panel-title a")
        body = panel.select_one(".panel-body")
        if title is None or body is None:
            continue
        raw_text = title.get_text(" ", strip=True)
        m = re.match(r"(\d+)\.\s*(.*)", raw_text)
        number, lemma = (int(m.group(1)), m.group(2)) if m else (None, raw_text)

        score = panel.select_one(".panel-title .label")
        score = int(score.get_text(strip=True)) if score and \
            re.fullmatch(r"-?\d+", score.get_text(strip=True)) else None

        vote = body.select_one("button.vote[id]")
        text, examples, author, age = None, [], None, None
        for p in body.find_all("p", recursive=False):
            small = p.find("small")
            italic = p.find("i")
            if small is not None:
                m2 = re.match(r"Enviado por (.*?)\s+(\S+ \w+ ago)\.?$",
                              small.get_text(" ", strip=True))
                if m2:
                    author, age = m2.group(1), m2.group(2)
                else:
                    age = small.get_text(" ", strip=True)
            elif italic is not None:
                examples = [e.strip() for e in italic.get_text("\n").split("\n") if e.strip()]
            elif text is None:
                text = p.get_text(" ", strip=True)

        definitions.append({
            "id_definicion": vote["id"] if vote else None,
            "numero": number,
            "lema": lemma,
            "puntaje": score,
            "texto": text,
            "ejemplos": examples,
            "autor": author,
            "antiguedad": age,
            "anio_aprox": approx_year(age, download_date),
            "url": url,
        })
    return definitions


def download(cfg, letters=None, cache_only=False, log=print):
    """Walks the indexes and the page of each term. Returns the list of index
    entries and the client (to count downloads)."""
    dcfg = cfg["diccionario_argentino"]
    client = common.CachedClient(CACHE_DIR, cfg["http"])
    letters = letters or dcfg["letras"]

    entries = []
    for letter in letters:
        url = f'{dcfg["base_url"]}/terms/{letter}'
        html = client.get(url, cache_only=cache_only)
        if html is None:
            log(f"  index {letter}: could not download")
            continue
        items = parse_index(html)
        log(f"  index {letter}: {len(items)} entries")
        entries += [{"letra": letter, "titulo": t, "url": u} for t, u in items]

    pending = [e for e in entries if not client.in_cache(e["url"])]
    log(f"  term pages: {len(entries)} ({len(pending)} not cached)")
    for i, e in enumerate(entries, 1):
        html = client.get(e["url"], cache_only=cache_only)
        e["descargada"] = html is not None
        e["definiciones"] = [] if html is None else \
            parse_term(html, e["url"], cache_date(e["url"]))
        if i % 250 == 0:
            log(f"    {i}/{len(entries)} (downloaded {client.downloads})")
    return entries, client


def cache_date(url):
    """Download date of a page, taken from its cache file."""
    path = common.cache_path(CACHE_DIR, url)
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
