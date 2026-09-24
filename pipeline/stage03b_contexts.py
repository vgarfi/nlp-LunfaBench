"""Stage 03b: contexts in song lyrics.

In steps, so each one can run separately:
1. genius: finds the Genius ID of each artist of stage 03a.
   Output: data/interim/artistas_genius.csv
2. songs: lists the songs of each artist (by popularity, only those where
   they are the primary artist). Metadata only: title, year, URL.
   Output: data/interim/canciones.jsonl
3. lyrics: chooses songs with caps per artist and per decade, downloads each
   lyric, searches all candidates and controls at once and stores each
   occurrence as a fragment of up to 25 words.
   Outputs: data/interim/contextos.jsonl, data/interim/indice_palabras.jsonl
   and data/interim/search_log_03b.csv.
The numbers of the three steps go to data/interim/03b_contextos_numeros.json.

a full lyric is NEVER written to disk or printed. It lives in
memory while the song is processed and is then discarded. On disk there are
only the fragments and, per song, the set of distinct words (no order or
repetitions: the lyric cannot be rebuilt from it), which tells which songs to
download again if the candidates change.

Usage:
    python -m pipeline.stage03b_contexts --step genius
    python -m pipeline.stage03b_contexts --step songs
    python -m pipeline.stage03b_contexts --step lyrics
"""

import argparse
import csv
import json
import os
import random
import re
import time
from collections import Counter, defaultdict

import requests
from bs4 import BeautifulSoup
from wordfreq import top_n_list

from pipeline import common
from pipeline import stage01_candidates as s01
from pipeline import stage02_layer as s02
from pipeline import stage02b_controls as s02b
from pipeline import stage03a_artists as s03a
from pipeline import source_genius as gn

GENIUS_ARTISTS = os.path.join(common.DATA_INTERIM, "artistas_genius.csv")
SONGS = os.path.join(common.DATA_INTERIM, "canciones.jsonl")
CONTEXTS = os.path.join(common.DATA_INTERIM, "contextos.jsonl")
WORD_INDEX = os.path.join(common.DATA_INTERIM, "indice_palabras.jsonl")
SEARCH_LOG = os.path.join(common.DATA_INTERIM, "search_log_03b.csv")
NUMBERS = os.path.join(common.DATA_INTERIM, "03b_contextos_numeros.json")


def step_genius(cfg, cache_only=False):
    """cache_only: use only the searches already made (pilot sample). Artists
    without a search are left with buscado = False."""
    cli = gn.client(cfg)
    with open(s03a.OUTPUT, encoding="utf-8") as f:
        artists = list(csv.DictReader(f))
    rows = []
    for i, a in enumerate(artists, 1):
        url = f'{gn.API}/search?' + gn.urlencode(sorted({"q": a["nombre"], "per_page": 20}.items()))
        searched = not cache_only or cli.in_cache(url)
        found = gn.find_artist(cli, a["nombre"], a["genius_slug"] or None,
                               cache_only=cache_only) if searched else None
        rows.append({**a, "buscado_en_genius": searched,
                     "genius_id": found[0] if found else "",
                     "genius_nombre": found[1] if found else "",
                     "genius_url": found[2] if found else ""})
        if i % 250 == 0:
            print(f"  {i}/{len(artists)} (in Genius: {sum(1 for x in rows if x['genius_id'])})",
                  flush=True)
    with open(GENIUS_ARTISTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    in_genius = [x for x in rows if x["genius_id"]]
    numbers = {
        "fecha": common.now_iso(),
        "artistas": len(rows),
        "buscados": sum(1 for x in rows if x["buscado_en_genius"]),
        "en_genius": len(in_genius),
        "en_genius_por_tipo": dict(Counter(x["tipo"] or "sin tipo" for x in in_genius)),
        "en_genius_por_fuente": dict(Counter(x["fuentes"] for x in in_genius)),
        "genius_ids_distintos": len({x["genius_id"] for x in in_genius}),
    }
    save_numbers({"genius": numbers})
    print(json.dumps(numbers, ensure_ascii=False))
    print(f"-> {GENIUS_ARTISTS}")


def is_valid_song(song, artist_id, exclude, ba_ids=None):
    """Only songs where the artist is the primary one, with complete lyrics,
    that are not remixes or live versions, and that are songs (Genius
    -annotated pages are calendars or transcription indexes). If the Genius
    IDs of the Buenos Aires artists are given, every primary artist has to
    be there: in the BZRP Music Sessions the primary artist is Bizarrap but
    the guest sings, and the guest can be from another country."""
    title = song.get("title") or ""
    primary_ids = {a.get("id") for a in song.get("primary_artists") or []} or \
        {(song.get("primary_artist") or {}).get("id")}
    return ((song.get("primary_artist") or {}).get("id") == artist_id
            and song.get("lyrics_state") == "complete"
            and not song.get("url", "").endswith("-annotated")
            and not any(x.lower() in title.lower() for x in exclude)
            and (ba_ids is None or primary_ids <= ba_ids))


def era(artist, cutoffs):
    """Era by decade of birth or formation: before 1930, 1930 to 1969, since
    1970, or no date."""
    if not artist["decada_origen"]:
        return "no date"
    d = int(artist["decada_origen"])
    return next((f"before {c}" for c in cutoffs if d < c), f"since {cutoffs[-1]}")


def pilot_sample(artists, ccfg):
    """Small sample for the EDA: up to N artists per era, drawn with a fixed
    seed, plus the artistas_extra of config.yaml (Gardel), who always get
    in."""
    rng = random.Random(ccfg["semilla"])
    by_era = defaultdict(list)
    for a in sorted(artists, key=lambda a: a["id"]):
        by_era[era(a, ccfg["cortes_de_epoca"])].append(a)
    chosen = [a for a in artists if a["fuente_origen"] == "excepcion_manual"]
    for group in by_era.values():
        rest = [a for a in group if a not in chosen]
        chosen += rng.sample(rest, min(ccfg["piloto_artistas_por_epoca"], len(rest)))
    print(f"  pilot sample: {len(chosen)} artists "
          f"({dict(Counter(era(a, ccfg['cortes_de_epoca']) for a in chosen))})", flush=True)
    return chosen


def step_songs(cfg):
    ccfg = cfg["etapa03b_contextos"]
    cli = gn.client(cfg)
    with open(GENIUS_ARTISTS, encoding="utf-8") as f:
        artists = [a for a in csv.DictReader(f) if a["genius_id"]]
    ba_ids = {int(a["genius_id"]) for a in artists}
    if ccfg.get("piloto_artistas_por_epoca"):
        artists = pilot_sample(artists, ccfg)
    # The same Genius artist can come from two rows (two spellings in
    # MusicBrainz): it is listed once.
    seen, rows = set(), []
    for i, a in enumerate(artists, 1):
        gid = int(a["genius_id"])
        if gid in seen:
            continue
        seen.add(gid)
        songs, page_num = [], 1
        while page_num and len(songs) < ccfg["canciones_por_artista"]:
            payload = gn.api(cli, f"artists/{gid}/songs", sort="popularity", per_page=50,
                             page=page_num)
            if not payload:
                break
            songs += [c for c in payload.get("songs", [])
                      if is_valid_song(c, gid, ccfg["excluir_titulos"], ba_ids)]
            page_num = payload.get("next_page")
        for order, c in enumerate(songs[:ccfg["canciones_por_artista"]], 1):
            date = c.get("release_date_components") or {}
            rows.append({
                "genius_song_id": c["id"], "titulo": c.get("title"), "url": c.get("url"),
                "anio_genius": date.get("year"), "orden_popularidad": order,
                "artista": a["nombre"], "artista_id": a["id"], "genius_artist_id": gid,
                "tipo_artista": a["tipo"], "origen": a["lugar_origen"],
                "fuente_origen": a["fuente_origen"], "generos": a["generos"],
                "musicbrainz_artista": a["musicbrainz"], "decada_origen_artista": a["decada_origen"],
                # Guests sing part of the lyric: if one of them is not from
                # Buenos Aires, the fragment may be theirs.
                "invitados": [x.get("name") for x in c.get("featured_artists") or []],
                "invitados_de_ba": all(x.get("id") in ba_ids
                                       for x in c.get("featured_artists") or []),
            })
        if i % 100 == 0:
            print(f"  {i}/{len(artists)} artists, {len(rows)} songs", flush=True)
    common.write_jsonl(SONGS, rows)
    years = Counter((c["anio_genius"] // 10 * 10) if c["anio_genius"] else "sin anio"
                    for c in rows)
    numbers = {
        "fecha": common.now_iso(),
        "artistas_listados": len(seen),
        "canciones": len(rows),
        "artistas_con_canciones": len({c["genius_artist_id"] for c in rows}),
        "canciones_por_decada_genius": {str(k): v for k, v in sorted(
            years.items(), key=lambda x: (isinstance(x[0], str), x[0]))},
    }
    save_numbers({"canciones": numbers})
    print(json.dumps(numbers, ensure_ascii=False))
    print(f"-> {SONGS}")


# --- Step 3: lyrics -------------------------------------------------------------

def search_forms(cfg):
    """{accent-free key: [(target, form, priority, exact)]}.

    Each candidate and each control is searched by its term, its spellings and
    merged variants (priority 0) and by its inflections in kaikki and
    Wikcionario: plurals, feminines and conjugations (priority 1). If a form
    belongs to one candidate and is an inflection of another, the own form
    wins (cheta is a separate candidate, even though it is the feminine of
    cheto).

    The search ignores accents and case, except when the accent-free word is
    one of the most frequent in Spanish: then the exact accent is required
    (sé is not se, papá is not papa)."""
    frequent = {common.search_key(w) for w in
                top_n_list("es", cfg["etapa03b_contextos"]["frecuentes_con_tilde_exacta"])}
    inverted = defaultdict(set)
    for _, module, _ in s02.LEXICAL_SOURCES:
        for word, entries in module.index(cfg).items():
            for e in entries:
                for a in e["acepciones"]:
                    for lemma in a["forma_de"]:
                        inverted[lemma].add(word)

    targets = []
    layers = {c["clave"]: c["capa_propuesta"] for c in common.read_jsonl(s02.OUTPUT)}
    for c in common.read_jsonl(s01.OUTPUT):
        own = {c["term"], *c["formas"]} | {f for v in c["variantes"] for f in v["formas"]}
        lemmas = own | set(c["kaikki"]["palabras"]) | set(c["wikcionario"]["palabras"])
        targets.append((f'cand:{c["clave"]}', c["term"], layers.get(c["clave"]), own, lemmas))
    for c in common.read_jsonl(s02b.OUTPUT):
        targets.append((f'ctrl:{c["clave"]}', c["term"], "control_negativo", {c["term"]},
                        {c["term"]}))

    forms = defaultdict(list)
    for target, _, _, own, lemmas in targets:
        inflections = {f for l in lemmas for f in inverted.get(l, ())} - own
        for priority, group in ((0, own), (1, inflections)):
            for form in group:
                form = common.normalize(form)
                if not form or " " in form:
                    continue
                key = common.search_key(form)
                forms[key].append((target, form, priority, key in frequent))
    info = {o: {"term": t, "capa": layer} for o, t, layer, _, _ in targets}
    return forms, info


def choose_target(options, token):
    """The target a word of the lyric belongs to, or None."""
    token_norm = common.normalize(token)
    valid_options = [o for o in options if not o[3] or o[1] == token_norm]
    if not valid_options:
        return None
    return min(valid_options, key=lambda o: (o[2], o[1] != token_norm, o[0]))


_ACCENTS = "áéíóúñÁÉÍÓÚÑ"
_EDGE = re.compile(r"^[^\w']+|[^\w']+$")


def fetch_lyrics(url, cfg, state):
    """Lines of the lyric, in memory only. None if it could not be fetched."""
    http = cfg["http"]
    for attempt in range(http["reintentos"]):
        wait = state["last"] + max(1.0, http["pausa_segundos"]) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(url, headers={"User-Agent": http["user_agent"]},
                             timeout=http["timeout_segundos"])
        except requests.RequestException:
            r = None
        finally:
            state["last"] = time.monotonic()
        if r is not None and r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            containers = soup.select('div[data-lyrics-container="true"]')
            for c in containers:
                for x in c.select('[data-exclude-from-selection="true"]'):
                    x.decompose()
                for br in c.find_all("br"):
                    br.replace_with("\n")
            text = common.normalize_homoglyphs("\n".join(c.get_text() for c in containers))
            return [l.strip() for l in text.split("\n")
                    if l.strip() and not re.fullmatch(r"\[.*\]", l.strip())]
        if r is not None and r.status_code == 404:
            return None
        time.sleep(max(1.0, http["pausa_segundos"]) * 5 * (2 ** attempt))
    return None


# Function words to recognize the language of a lyric. The filter of the
# previous scraper required more than 5 occurrences of que/para/con/pero/no
# and discarded short Spanish lyrics; now it looks at the proportion.
_FUNCTION_WORDS = {
    "es": {"de", "la", "que", "el", "en", "y", "los", "se", "del", "las", "un", "por", "con",
           "no", "una", "su", "para", "es", "al", "lo", "como", "más", "pero", "sus", "le",
           "ya", "me", "mi", "te", "tu", "yo", "si", "sin", "cuando", "todo", "nos", "hay",
           "vos", "sos", "qué", "voy", "está", "esta", "eso", "porque"},
    "en": {"the", "and", "you", "i", "to", "of", "it", "my", "is", "that", "on", "your",
           "for", "be", "with", "all", "we", "this", "don't", "i'm", "what", "was", "are"},
    "pt": {"não", "você", "pra", "muito", "minha", "então", "isso", "é", "eu", "meu", "uma",
           "também", "vai", "tá", "coração", "nós"},
}


def validate_lyrics(lines):
    """None if the lyric is usable, or the reason to discard it."""
    text = " " + " ".join(lines).lower() + " "
    # Old transcriptions with ALL accents removed: they ruin the quote.
    suspicious = sum(1 for s in (" mas ", " asi ", " aqui ", " tambien ") if s in text)
    if suspicious >= 2 and not any(c in text for c in _ACCENTS):
        return "transcripcion sin tildes"
    # Language: enough Spanish function words and many more than English or
    # Portuguese ones (this also discards instrumental music pages, which
    # carry descriptive text or nothing).
    tokens = [_EDGE.sub("", w) for w in text.split()]
    counts = {language: sum(t in words for t in tokens)
              for language, words in _FUNCTION_WORDS.items()}
    if len(tokens) < 20 or counts["es"] < max(4, 0.12 * len(tokens)) or \
            counts["es"] < 2 * max(counts["en"], counts["pt"]):
        return "no parece espanol"
    return None


def fragments(lines, forms, cfg):
    """(target, form_in_lyric, fragment) for each occurrence. The term appears
    only once in the fragment; if the window of lines repeats it, the window
    shrinks around the occurrence."""
    ccfg = cfg["etapa03b_contextos"]
    max_words, context = ccfg["max_palabras_fragmento"], ccfg["lineas_de_contexto"]
    words = [l.split() for l in lines]
    targets = [[None] * len(p) for p in words]
    for i, p in enumerate(words):
        for j, w in enumerate(p):
            token = _EDGE.sub("", w)
            options = forms.get(common.search_key(token)) if token else None
            if options:
                picked = choose_target(options, token)
                targets[i][j] = picked[0] if picked else None

    output = []
    for i, p in enumerate(words):
        for j, target in enumerate(targets[i]):
            if target is None:
                continue
            # Window of lines, flattened with a separator between lines.
            window = []
            for k in range(max(0, i - context), min(len(lines), i + context + 1)):
                if window:
                    window.append(("/", None, False))
                window += [(w, targets[k][m], (k, m) == (i, j)) for m, w in enumerate(words[k])]
            center = next(n for n, x in enumerate(window) if x[2])
            # Trim around the occurrence, without other occurrences of the term.
            lo = max((n for n in range(center) if window[n][1] == target), default=-1) + 1
            hi = min((n for n in range(center + 1, len(window)) if window[n][1] == target),
                     default=len(window))
            segment = window[lo:hi]
            center -= lo
            word_positions = [n for n, x in enumerate(segment) if x[0] != "/"]
            if len(word_positions) > max_words:
                pos = word_positions.index(center)
                start_idx = max(0, min(pos - max_words // 2, len(word_positions) - max_words))
                segment = segment[word_positions[start_idx]:word_positions[start_idx + max_words - 1] + 1]
            text = " ".join(x[0] for x in segment).strip(" /")
            if len([x for x in segment if x[0] != "/"]) >= ccfg["min_palabras_fragmento"]:
                output.append((target, _EDGE.sub("", words[i][j]), text))
    return output


def choose_songs(songs, cfg):
    """Caps per artist and per decade (Genius year), so that a couple of
    artists or recent urban music do not dominate. Songs are walked in order
    of popularity, interleaving artists."""
    ccfg = cfg["etapa03b_contextos"]
    by_artist, by_decade, chosen = Counter(), Counter(), []
    for c in sorted(songs, key=lambda c: (c["orden_popularidad"], c["genius_artist_id"])):
        decade = c["anio_genius"] // 10 * 10 if c["anio_genius"] else "no_year"
        cap = ccfg["max_canciones_sin_anio"] if decade == "no_year" \
            else ccfg["max_canciones_por_decada"]
        if by_artist[c["genius_artist_id"]] >= ccfg["max_canciones_por_artista"] or \
                by_decade[decade] >= cap:
            continue
        by_artist[c["genius_artist_id"]] += 1
        by_decade[decade] += 1
        chosen.append(c)
    return chosen


def forget_discarded(reason):
    """Removes from the index and the log the songs discarded for a reason,
    so the lyrics step processes them again."""
    index = [x for x in common.read_jsonl(WORD_INDEX) if x["descartada"] != reason]
    common.write_jsonl(WORD_INDEX, index)
    with open(SEARCH_LOG, encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if len(r) < 5 or r[4] != reason]
    with open(SEARCH_LOG, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def step_lyrics(cfg, retry=None):
    if retry:
        forget_discarded(retry)
    forms, info = search_forms(cfg)
    songs = choose_songs(list(common.read_jsonl(SONGS)), cfg)
    done = {x["genius_song_id"] for x in common.read_jsonl(WORD_INDEX)} \
        if os.path.exists(WORD_INDEX) else set()
    pending = [c for c in songs if c["genius_song_id"] not in done]
    print(f"  chosen songs: {len(songs)}, already processed: {len(done)}, "
          f"pending: {len(pending)}", flush=True)

    # Cap of fragments per term: a common verb (saber) shows up in almost
    # every lyric. With the word index one can go back for more.
    by_target = Counter(x["objetivo"] for x in common.read_jsonl(CONTEXTS)) \
        if os.path.exists(CONTEXTS) else Counter()
    cap = cfg["etapa03b_contextos"]["max_fragmentos_por_termino"]
    new_log = not os.path.exists(SEARCH_LOG)
    state = {"last": 0.0}
    with open(CONTEXTS, "a", encoding="utf-8") as f_ctx, \
            open(WORD_INDEX, "a", encoding="utf-8") as f_idx, \
            open(SEARCH_LOG, "a", newline="", encoding="utf-8") as f_log:
        log = csv.writer(f_log)
        if new_log:
            log.writerow(["genius_song_id", "titulo", "artista", "anio_genius", "estado",
                          "apariciones"])
        for n, c in enumerate(pending, 1):
            lines = fetch_lyrics(c["url"], cfg, state)
            reason = "no se pudo bajar" if lines is None else validate_lyrics(lines)
            occurrences = []
            if not reason:
                seen = set()
                for target, form, text in fragments(lines, forms, cfg):
                    if (target, text) in seen or by_target[target] >= cap:
                        continue  # repeated chorus or term already covered
                    seen.add((target, text))
                    by_target[target] += 1
                    occurrences.append((target, form, text))
                words = sorted({common.search_key(_EDGE.sub("", w))
                                for l in lines for w in l.split()} - {""})
            del lines  # the full lyric never leaves this function
            for target, form, text in occurrences:
                f_ctx.write(json.dumps({
                    "objetivo": target, "term": info[target]["term"],
                    "layer": info[target]["capa"], "forma_en_letra": form,
                    "context": text, "context_source": "letra",
                    "source": {"song": c["titulo"], "artist": c["artista"],
                               "artist_id": c["artista_id"], "artist_origin": c["origen"],
                               "origin_source": c["fuente_origen"],
                               "genius_song_id": c["genius_song_id"], "url": c["url"],
                               "genius_release_year": c["anio_genius"], "year": None,
                               "invitados": c["invitados"],
                               "invitados_de_ba": c["invitados_de_ba"]},
                    "genre": c["generos"],
                    "pipeline": {"stage": "03b_contextos", "fecha": common.now_iso(),
                                 "validated_sense": False},
                }, ensure_ascii=False) + "\n")
            f_idx.write(json.dumps({"genius_song_id": c["genius_song_id"],
                                    "descartada": reason,
                                    "palabras": [] if reason else words},
                                   ensure_ascii=False) + "\n")
            log.writerow([c["genius_song_id"], c["titulo"], c["artista"], c["anio_genius"],
                          reason or "ok", len(occurrences)])
            if n % 50 == 0:
                for x in (f_ctx, f_idx, f_log):
                    x.flush()
                print(f"  {n}/{len(pending)}", flush=True)
    summarize_lyrics(songs, info)


def summarize_lyrics(songs, info):
    contexts = list(common.read_jsonl(CONTEXTS))
    index = list(common.read_jsonl(WORD_INDEX))
    by_layer = defaultdict(set)
    for x in contexts:
        by_layer[x["layer"]].add(x["objetivo"])
    total_by_layer = Counter(v["capa"] for v in info.values())
    lengths = [len(x["context"].replace(" / ", " ").split()) for x in contexts]
    # The terms were searched in these: the discarded ones do not count.
    in_spanish = {x["genius_song_id"] for x in index if not x["descartada"]}
    numbers = {
        "fecha": common.now_iso(),
        "canciones_elegidas": len(songs),
        "canciones_procesadas": len(index),
        "descartadas": dict(Counter(x["descartada"] for x in index if x["descartada"])),
        "canciones_en_espanol": len(in_spanish),
        "artistas_en_espanol": len({c["artista"] for c in songs
                                    if c["genius_song_id"] in in_spanish}),
        "fragmentos": len(contexts),
        "fragmentos_por_capa": dict(Counter(x["layer"] for x in contexts)),
        "terminos_con_contexto_por_capa": {
            layer: {"con_contexto": len(by_layer.get(layer, ())), "total": n}
            for layer, n in total_by_layer.items()},
        "largo_fragmento": {"mediana": sorted(lengths)[len(lengths) // 2] if lengths else None,
                            "min": min(lengths, default=None), "max": max(lengths, default=None)},
        "fragmentos_por_decada_genius": dict(sorted(Counter(
            str(x["source"]["genius_release_year"] // 10 * 10)
            if x["source"]["genius_release_year"] else "sin anio" for x in contexts).items())),
    }
    save_numbers({"letras": numbers})
    print(json.dumps(numbers, ensure_ascii=False, indent=2))


def save_numbers(new_items):
    numbers = {}
    if os.path.exists(NUMBERS):
        with open(NUMBERS, encoding="utf-8") as f:
            numbers = json.load(f)
    numbers.update(new_items)
    os.makedirs(common.DATA_INTERIM, exist_ok=True)
    with open(NUMBERS, "w", encoding="utf-8") as f:
        json.dump(numbers, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--step", choices=["genius", "songs", "lyrics"], required=True)
    ap.add_argument("--cache-only", action="store_true",
                    help="genius step: use only the searches already made (pilot sample)")
    ap.add_argument("--retry", metavar="REASON",
                    help="lyrics step: process again the songs discarded for this reason")
    args = ap.parse_args()
    cfg = common.load_config()
    if args.step == "genius":
        step_genius(cfg, cache_only=args.cache_only)
    elif args.step == "lyrics":
        step_lyrics(cfg, retry=args.retry)
    else:
        step_songs(cfg)


if __name__ == "__main__":
    main()
