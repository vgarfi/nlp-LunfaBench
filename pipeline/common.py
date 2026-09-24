"""Utilities shared by the pipeline stages: paths, configuration, text
normalization and an HTTP client with a cache and pauses."""

import gzip
import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW = os.path.join(REPO_ROOT, "data", "raw")
DATA_INTERIM = os.path.join(REPO_ROOT, "data", "interim")
REPORTS = os.path.join(REPO_ROOT, "reports")


def load_env(path=os.path.join(REPO_ROOT, ".env")):
    """Loads the variables of the local .env without overriding the
    environment. """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def load_config(path=os.path.join(REPO_ROOT, "config.yaml")):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Normalization ---------------------------------------------------------
# Project rule: search ignoring accents and case, but always keep the
# original form.

# Genius (and sometimes user contributions) contains stray Cyrillic
# homoglyphs. Same map as scripts/genius_scraper.py.
HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "і": "i", "һ": "h", "Α": "A",
    "Ε": "E", "Ο": "O", "Р": "P", "С": "C", "Х": "X",
}


def normalize_homoglyphs(text: str) -> str:
    return "".join(HOMOGLYPHS.get(ch, ch) for ch in text)


def normalize(text: str) -> str:
    """Canonical form that keeps accents: NFC, no homoglyphs, lowercase and
    collapsed whitespace."""
    text = normalize_homoglyphs(unicodedata.normalize("NFC", text))
    return re.sub(r"\s+", " ", text).strip().lower()


def strip_accents(text: str) -> str:
    """Key for comparing without accents. The eñe is not an accent: it is
    kept."""
    text = text.replace("ñ", "\0").replace("Ñ", "\1")
    base = "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", base.replace("\0", "ñ").replace("\1", "Ñ"))


def search_key(text: str) -> str:
    return strip_accents(normalize(text))


# --- Glosses ---------------------------------------------------------------

# Stopwords in English (kaikki) and in Spanish (Wikcionario).
_STOPWORDS = {"a", "an", "the", "of", "to", "or", "and", "in", "on", "for", "with", "as",
              "by", "from", "that", "which", "who", "is", "be", "it", "its", "one", "sth",
              "something", "someone", "somebody", "esp", "especially", "etc",
              "de", "la", "el", "los", "las", "un", "una", "y", "o", "que", "en", "del", "al",
              "por", "con", "para", "se", "su", "sus", "lo", "como", "es", "algo", "alguien",
              "dicho", "persona", "cosa", "extension", "especialmente"}


def gloss_words(glosses):
    """Content words of a gloss, without accents and without a final -s
    (chicos and chico count as the same word)."""
    words = {strip_accents(w) for g in glosses for w in re.findall(r"[a-záéíóúüñ]+", g.lower())}
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words - _STOPWORDS}


def same_gloss(a, b, threshold):
    """Two lists of glosses describe the same sense if they share at least
    this proportion of content words (Jaccard). Only meaningful within one
    language."""
    pa, pb = gloss_words(a), gloss_words(b)
    return bool(pa and pb) and len(pa & pb) / len(pa | pb) >= threshold


def share_meaning(definitions_a, definitions_b, threshold):
    """Whether some definition of a and some of b talk about the same thing:
    the shared part is at least this proportion of the shorter one. More
    tolerant than same_gloss, because the definitions of the collaborative
    dictionary are free text of very different lengths."""
    for a in definitions_a:
        pa = gloss_words([a])
        for b in definitions_b:
            pb = gloss_words([b])
            if pa and pb and len(pa & pb) / min(len(pa), len(pb)) >= threshold:
                return True
    return False


# --- JSONL -----------------------------------------------------------------

def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# --- HTTP with a cache -----------------------------------------------------

def cache_path(cache_dir, url):
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, h[:2], h + ".html.gz")


class CachedClient:
    """Downloads pages one at a time, with a minimum pause between requests
    and a local on-disk cache (gzip), so rerunning a stage does not repeat
    downloads."""

    def __init__(self, cache_dir, cfg_http, headers=None):
        """headers: extra headers for every request (for example an API
        authorization). They are not part of the cache key and are never
        stored."""
        self.cache_dir = cache_dir
        self.pause = max(1.0, float(cfg_http["pausa_segundos"]))
        self.timeout = cfg_http["timeout_segundos"]
        self.retries = cfg_http["reintentos"]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = cfg_http["user_agent"]
        self.session.headers.update(headers or {})
        self._last = 0.0
        self.downloads = 0
        self.from_cache = 0
        os.makedirs(cache_dir, exist_ok=True)

    def in_cache(self, url):
        return os.path.exists(cache_path(self.cache_dir, url))

    def get(self, url, cache_only=False):
        """Returns the HTML of the url, or None if it could not be fetched."""
        cache_file = cache_path(self.cache_dir, url)
        if os.path.exists(cache_file):
            self.from_cache += 1
            with gzip.open(cache_file, "rt", encoding="utf-8") as f:
                return f.read()
        if cache_only:
            return None

        for attempt in range(self.retries):
            wait = self._last + self.pause - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.session.get(url, timeout=self.timeout)
            except requests.RequestException:
                r = None
            finally:
                self._last = time.monotonic()
            if r is not None and r.status_code == 200:
                # Without a charset in the header, requests assumes latin-1
                # and breaks the accents: try utf-8 first.
                try:
                    html = r.content.decode("utf-8")
                except UnicodeDecodeError:
                    html = r.text
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                tmp = cache_file + ".tmp"
                with gzip.open(tmp, "wt", encoding="utf-8") as f:
                    f.write(html)
                os.replace(tmp, cache_file)
                self.downloads += 1
                return html
            if r is not None and r.status_code == 404:
                return None
            # 429, 5xx or a network error: wait longer each time before retrying
            time.sleep(self.pause * 5 * (2 ** attempt))
        return None
