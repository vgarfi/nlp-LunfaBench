"""Requests to the MusicBrainz API, with a local cache and pauses.

MusicBrainz allows at most one request per second and asks for a User-Agent
that identifies the application; the cached client of common does both.
Responses are stored in data/raw/musicbrainz/.
"""

import json
import os
from urllib.parse import urlencode

from pipeline import common

CACHE_DIR = os.path.join(common.DATA_RAW, "musicbrainz")


def client(cfg):
    return common.CachedClient(CACHE_DIR, cfg["http"])


def fetch(cli, cfg, resource, **params):
    """GET /ws/2/<resource> as JSON; None if it failed."""
    params["fmt"] = "json"
    url = f'{cfg["musicbrainz"]["base_url"]}/{resource}?{urlencode(sorted(params.items()))}'
    text = cli.get(url)
    return json.loads(text) if text else None


def paginate(cli, cfg, resource, key, **params):
    """Every result of a search or a listing, 100 at a time."""
    offset, results = 0, []
    while True:
        payload = fetch(cli, cfg, resource, limit=100, offset=offset, **params)
        if not payload:
            break
        page_items = payload.get(key, [])
        results += page_items
        total = payload.get("count", payload.get(f"{resource}-count", 0))
        offset += len(page_items)
        if not page_items or offset >= total:
            break
    return results
