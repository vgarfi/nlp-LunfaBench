"""Client for the Genius API.

The API gives metadata (artists, songs, dates, URLs) but not the lyrics. Only
those JSON responses are cached, in data/raw/genius/api/: they contain no
lyrics. Lyrics are fetched separately, used in memory and discarded.

The token is read from GENIUS_TOKEN (in .env).
"""

import json
import os
from urllib.parse import urlencode

from pipeline import common

CACHE_DIR = os.path.join(common.DATA_RAW, "genius", "api")
API = "https://api.genius.com"


def client(cfg):
    common.load_env()
    token = os.environ.get("GENIUS_TOKEN")
    if not token:
        raise SystemExit("GENIUS_TOKEN is missing from the .env at the repo root.")
    return common.CachedClient(CACHE_DIR, cfg["http"],
                               headers={"Authorization": f"Bearer {token}"})


def api(cli, path, cache_only=False, **params):
    """API response as a dict; None if it failed (or if it is not cached and
    cache_only was requested)."""
    url = f"{API}/{path}" + (f"?{urlencode(sorted(params.items()))}" if params else "")
    text = cli.get(url, cache_only=cache_only)
    return json.loads(text)["response"] if text else None


def find_artist(cli, name, slug=None, cache_only=False):
    """(id, name on Genius, url) of the artist, or None. Searches songs with
    the name and keeps the primary artist whose name matches (ignoring
    accents and case) or whose slug is the one in Wikidata (P2373)."""
    payload = api(cli, "search", cache_only=cache_only, q=name, per_page=20)
    if not payload:
        return None
    key = common.search_key(name)
    candidates = {}
    for hit in payload.get("hits", []):
        a = hit.get("result", {}).get("primary_artist") or {}
        if not a.get("id"):
            continue
        slug_matches = slug and a.get("url", "").rstrip("/").split("/")[-1].lower() == slug.lower()
        if slug_matches or common.search_key(a.get("name", "")) == key:
            candidates.setdefault(a["id"], [a, 0, bool(slug_matches)])[1] += 1
    if not candidates:
        return None
    # First the one that matches by slug, then the one with the most songs.
    a, _, _ = max(candidates.values(), key=lambda c: (c[2], c[1]))
    return a["id"], a["name"], a.get("url", "")
