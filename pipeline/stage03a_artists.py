"""Stage 03a: artists from Buenos Aires.

Builds the list of artists whose lyrics are searched in stage 03b. The rule
is strict and automatic: an artist gets in only if their origin is at city
level in Buenos Aires (the city or the 24 partidos of the conurbano). Those
with only "Argentina" or "provincia de Buenos Aires" are left out.

Sources, with the provenance of each artist's origin:
- Wikidata: people with a musical occupation born (P19) in a place of Gran
  Buenos Aires and groups formed (P740) there. It also brings dates, genres,
  the Genius ID (P2373) and the MusicBrainz ID (P434).
- MusicBrainz: artists whose area or area of origin (begin-area) is a place
  of Gran Buenos Aires. Filtered by area ID, not by name: there is another
  Buenos Aires in Costa Rica.

A Wikidata artist and a MusicBrainz artist are joined only if Wikidata has
the MusicBrainz ID (never by name). The artists in artistas_extra of
config.yaml (Gardel) get in even if the rule leaves them out.

Outputs:
- data/interim/artistas.csv
- data/interim/03a_artistas_numeros.json

Usage:
    python -m pipeline.stage03a_artists
"""

import csv
import json
import os
from collections import Counter

from pipeline import common
from pipeline import source_musicbrainz as mb
from pipeline import source_wikidata as wd

OUTPUT = os.path.join(common.DATA_INTERIM, "artistas.csv")
POSSIBLE_EXCEPTIONS = os.path.join(common.DATA_INTERIM, "artistas_posibles_excepciones.csv")
NUMBERS = os.path.join(common.DATA_INTERIM, "03a_artistas_numeros.json")

# MusicBrainz types that are not recording artists (fictional characters).
_EXCLUDED_MB_TYPES = {"Character"}


def metro_areas(cfg):
    """The city and the 24 partidos: the parts (P527) of Gran Buenos Aires."""
    rows = wd.run_query(f"""
        SELECT ?area ?areaLabel WHERE {{
          wd:{cfg["wikidata"]["area_metropolitana"]} wdt:P527 ?area .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
        }}""", cfg)
    return {f["area"]: f["areaLabel"] for f in rows}


def wikidata_people(cfg, areas):
    """People with a musical occupation born in a place inside the areas.
    Occupations: musician and singer with their subclasses, plus a few more
    (composer, lyricist, rapper...). It is queried in simple steps (born in
    Argentina, then the area filter) because the combined query does not
    finish within the time Wikidata allows."""
    w = cfg["wikidata"]
    rows = wd.run_query(f"""
        SELECT DISTINCT ?x ?lugar WHERE {{
          VALUES ?raiz {{ {wd.values_block(w["ocupaciones_raiz"])} }}
          ?ocupacion wdt:P279* ?raiz .
          ?x wdt:P106 ?ocupacion ; wdt:P19 ?lugar .
          ?lugar wdt:P17 wd:Q414 .
        }}""", cfg)
    rows += wd.run_query(f"""
        SELECT DISTINCT ?x ?lugar WHERE {{
          VALUES ?ocupacion {{ {wd.values_block(w["ocupaciones_extra"])} }}
          ?x wdt:P106 ?ocupacion ; wdt:P19 ?lugar .
          ?lugar wdt:P17 wd:Q414 .
        }}""", cfg)
    return filter_by_area(cfg, rows, areas)


def wikidata_groups(cfg, areas):
    """Groups (musical group and its subclasses) formed in a place inside the
    areas."""
    rows = wd.run_query(f"""
        SELECT DISTINCT ?x ?lugar WHERE {{
          ?x wdt:P31/wdt:P279* wd:{cfg["wikidata"]["clase_grupo"]} ; wdt:P740 ?lugar .
          ?lugar wdt:P17 wd:Q414 .
        }}""", cfg)
    return filter_by_area(cfg, rows, areas)


def filter_by_area(cfg, rows, areas, batch=200):
    """Keeps the rows whose place is inside one of the areas (the place
    itself, a barrio or a town of a partido)."""
    places = sorted({f["lugar"] for f in rows})
    area_of = {}
    for i in range(0, len(places), batch):
        for r in wd.run_query(f"""
                SELECT ?lugar ?area WHERE {{
                  VALUES ?lugar {{ {wd.values_block(places[i:i + batch])} }}
                  VALUES ?area {{ {wd.values_block(areas)} }}
                  ?lugar wdt:P131* ?area .
                }}""", cfg):
            area_of[r["lugar"]] = r["area"]
    return [dict(f, area=area_of[f["lugar"]]) for f in rows if f["lugar"] in area_of]


def wikidata_details(cfg, qids, batch=150):
    """Name, dates, genres and Genius and MusicBrainz IDs, in batches."""
    details = {}
    qids = sorted(qids)
    for i in range(0, len(qids), batch):
        rows = wd.run_query(f"""
            SELECT ?x (SAMPLE(?nombre_) AS ?nombre) (SAMPLE(?nac) AS ?nacimiento)
                   (SAMPLE(?fund) AS ?fundacion) (SAMPLE(?ini) AS ?inicio_actividad)
                   (SAMPLE(?gen) AS ?genius)
                   (GROUP_CONCAT(DISTINCT ?mb; separator="|") AS ?mbids)
                   (GROUP_CONCAT(DISTINCT ?genero; separator="|") AS ?generos) WHERE {{
              VALUES ?x {{ {wd.values_block(qids[i:i + batch])} }}
              OPTIONAL {{ ?x rdfs:label ?es FILTER(LANG(?es) = "es") }}
              OPTIONAL {{ ?x rdfs:label ?en FILTER(LANG(?en) = "en") }}
              BIND(COALESCE(?es, ?en) AS ?nombre_)
              OPTIONAL {{ ?x wdt:P569 ?nac }}
              OPTIONAL {{ ?x wdt:P571 ?fund }}
              OPTIONAL {{ ?x wdt:P2031 ?ini }}
              OPTIONAL {{ ?x wdt:P2373 ?gen }}
              OPTIONAL {{ ?x wdt:P434 ?mb }}
              OPTIONAL {{ ?x wdt:P136 ?g . ?g rdfs:label ?genero FILTER(LANG(?genero) = "es") }}
            }} GROUP BY ?x""", cfg)
        for f in rows:
            details[f["x"]] = f
    return details


def labels(cfg, qids, batch=200):
    qids = sorted(qids)
    output = {}
    for i in range(0, len(qids), batch):
        for f in wd.run_query(f"""
                SELECT ?x ?xLabel WHERE {{
                  VALUES ?x {{ {wd.values_block(qids[i:i + batch])} }}
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
                }}""", cfg):
            output[f["x"]] = f["xLabel"]
    return output


def musicbrainz_areas(cfg, cli, areas):
    """MusicBrainz IDs of the places of Gran Buenos Aires: the city, its
    barrios ('part of' relations in MusicBrainz) and the places that Wikidata
    links to MusicBrainz (P982)."""
    city = cfg["musicbrainz"]["area_ciudad"]
    names = {}
    payload = mb.fetch(cli, cfg, f"area/{city}", inc="area-rels")
    names[city] = payload["name"]
    for r in payload.get("relations", []):
        if r.get("type") == "part of" and r.get("direction") == "forward":
            names[r["area"]["id"]] = r["area"]["name"]
    # In two steps (places of Argentina with a MusicBrainz ID, then the area
    # filter): the combined query does not finish in time.
    places = filter_by_area(cfg, [{"x": f["mb"], "lugar": f["lugar"]} for f in wd.run_query("""
            SELECT DISTINCT ?lugar ?mb WHERE { ?lugar wdt:P982 ?mb ; wdt:P17 wd:Q414 . }""", cfg)],
                               areas)
    place_names = labels(cfg, {f["lugar"] for f in places})
    for f in places:
        names.setdefault(f["x"], place_names.get(f["lugar"], f["lugar"]))
    return names


def musicbrainz_artists(cfg, cli, mb_areas, log=print):
    """Artists with an area in Gran Buenos Aires (listing by area) or with
    their area of origin there (search by name and filter by ID)."""
    def origin(a):
        # The area of origin (birth or formation) is the most reliable data.
        # The listing by area also brings those who died here (end-area):
        # Julio Sosa, Piazzolla. Those do not get in.
        if (a.get("begin-area") or {}).get("id") in mb_areas:
            return "musicbrainz:begin-area"
        if (a.get("area") or {}).get("id") in mb_areas:
            return "musicbrainz:area"
        return None

    matches, discarded = {}, {}
    for area_id in sorted(mb_areas):
        for a in mb.paginate(cli, cfg, "artist", "artists", area=area_id):
            if origin(a):
                matches[a["id"]] = (a, origin(a))
            else:
                discarded[a["id"]] = a
    log(f"  musicbrainz by area: {len(matches)} (left out {len(discarded)} without an origin here)")
    for area_id, name in sorted(mb_areas.items()):
        for a in mb.paginate(cli, cfg, "artist", "artists", query=f'beginarea:"{name}"'):
            if origin(a):
                matches[a["id"]] = (a, origin(a))
    log(f"  musicbrainz by area or area of origin: {len(matches)}")
    valid = {k: v for k, v in matches.items() if v[0].get("type") not in _EXCLUDED_MB_TYPES}
    return valid, {k: a for k, a in discarded.items() if k not in matches}


def extra_artists(cfg, cli, rows):
    """Rows for the artists in artistas_extra of config.yaml that did not get
    in through the rule, with fuente_origen = excepcion_manual."""
    already = {f["wikidata"] for f in rows if f["wikidata"]} | \
        {f["musicbrainz"] for f in rows if f["musicbrainz"]}
    requested = [r for r in (cfg.get("etapa03a_artistas") or {}).get("artistas_extra") or []
                 if r["wikidata"] not in already and r["musicbrainz"] not in already]
    details = wikidata_details(cfg, {r["wikidata"] for r in requested if r["wikidata"]})
    new_rows = []
    for r in requested:
        d = details.get(r["wikidata"], {})
        a = mb.fetch(cli, cfg, f'artist/{r["musicbrainz"]}') if r["musicbrainz"] else {}
        date = d.get("nacimiento") or d.get("fundacion") or (a.get("life-span") or {}).get("begin")
        new_rows.append({
            "id": f'wd:{r["wikidata"]}' if r["wikidata"] else f'mb:{r["musicbrainz"]}',
            "nombre": d.get("nombre") or r["nombre"],
            "tipo": "persona" if d.get("nacimiento") or a.get("type") == "Person" else "grupo",
            "lugar_origen": "", "area_origen": "", "fuente_origen": "excepcion_manual",
            "fecha_origen": (date or "")[:10], "decada_origen": decade(date),
            "generos": d.get("generos") or "", "wikidata": r["wikidata"],
            "musicbrainz": r["musicbrainz"], "genius_slug": d.get("genius") or "",
            "fuentes": "excepcion",
        })
    return new_rows


def decade(date):
    """'1890-12-11T00:00:00Z' or '1994-10-05' -> 1890; None if missing."""
    if not date:
        return None
    year = date.lstrip("+-")[:4]
    return int(year) // 10 * 10 if year.isdigit() else None


def main():
    cfg = common.load_config()
    print("wikidata")
    areas = metro_areas(cfg)
    print(f"  areas: {len(areas)} (city and partidos)")
    people = wikidata_people(cfg, list(areas))
    groups = wikidata_groups(cfg, list(areas))
    print(f"  people: {len({p['x'] for p in people})}, groups: {len({g['x'] for g in groups})}")
    origin = {}
    for rows, kind, prop in ((people, "persona", "P19"), (groups, "grupo", "P740")):
        for f in rows:
            origin.setdefault(f["x"], (kind, f["lugar"], f["area"], f"wikidata:{prop}"))
    details = wikidata_details(cfg, set(origin))
    place_names = labels(cfg, {o[1] for o in origin.values()})

    print("musicbrainz")
    cli = mb.client(cfg)
    mb_areas = musicbrainz_areas(cfg, cli, list(areas))
    print(f"  musicbrainz areas: {len(mb_areas)}")
    from_mb, without_origin = musicbrainz_artists(cfg, cli, mb_areas)

    # Union: Wikidata first; a MusicBrainz artist is joined to a Wikidata
    # one only if Wikidata has its ID (P434).
    rows, mbid_to_qid = [], {}
    for qid, (kind, place, area, origin_source) in sorted(origin.items()):
        d = details.get(qid, {})
        mbids = [m for m in (d.get("mbids") or "").split("|") if m]
        for m in mbids:
            mbid_to_qid[m] = qid
        date = d.get("nacimiento") if kind == "persona" else d.get("fundacion")
        date = date or d.get("inicio_actividad")
        rows.append({
            "id": f"wd:{qid}", "nombre": d.get("nombre") or qid, "tipo": kind,
            "lugar_origen": place_names.get(place, place), "area_origen": areas.get(area, area),
            "fuente_origen": origin_source, "fecha_origen": (date or "")[:10],
            "decada_origen": decade(date), "generos": d.get("generos") or "",
            "wikidata": qid, "musicbrainz": mbids[0] if mbids else "",
            "genius_slug": d.get("genius") or "", "fuentes": "wikidata",
        })
    by_qid = {f["wikidata"]: f for f in rows}
    for mbid, (a, origin_source) in sorted(from_mb.items()):
        if mbid in mbid_to_qid:
            row = by_qid[mbid_to_qid[mbid]]
            row["fuentes"] = "wikidata+musicbrainz"
            row["musicbrainz"] = mbid
            continue
        place = (a.get("begin-area") if origin_source.endswith("begin-area") else a.get("area")) or {}
        begin = (a.get("life-span") or {}).get("begin")
        rows.append({
            "id": f"mb:{mbid}", "nombre": a["name"],
            "tipo": "persona" if a.get("type") == "Person" else "grupo" if a.get("type") else "",
            "lugar_origen": place.get("name", ""), "area_origen": mb_areas.get(place.get("id"), ""),
            "fuente_origen": origin_source, "fecha_origen": begin or "",
            "decada_origen": decade(begin),
            "generos": "|".join(t["name"] for t in sorted(a.get("tags", []),
                                                          key=lambda t: -t.get("count", 0))[:5]),
            "wikidata": "", "musicbrainz": mbid, "genius_slug": "", "fuentes": "musicbrainz",
        })
    rows += extra_artists(cfg, cli, rows)

    # For the group to review: artists that MusicBrainz links to Buenos
    # Aires but not through their origin (usually, they died here).
    with open(POSSIBLE_EXCEPTIONS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nombre", "musicbrainz", "tipo", "area", "area_de_origen", "area_final",
                    "inicio", "fin"])
        for mbid, a in sorted(without_origin.items(), key=lambda x: x[1]["name"]):
            life = a.get("life-span") or {}
            w.writerow([a["name"], mbid, a.get("type") or "", (a.get("area") or {}).get("name", ""),
                        (a.get("begin-area") or {}).get("name", ""),
                        (a.get("end-area") or {}).get("name", ""),
                        life.get("begin", ""), life.get("end", "")])

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    numbers = {
        "fecha": common.now_iso(),
        "areas_wikidata": len(areas),
        "areas_musicbrainz": len(mb_areas),
        "artistas": len(rows),
        "por_fuente": dict(Counter(f["fuentes"] for f in rows)),
        "por_tipo": dict(Counter(f["tipo"] or "sin tipo" for f in rows)),
        "por_fuente_de_origen": dict(Counter(f["fuente_origen"] for f in rows)),
        "con_id_de_genius": sum(1 for f in rows if f["genius_slug"]),
        "con_id_de_musicbrainz": sum(1 for f in rows if f["musicbrainz"]),
        "por_decada_de_origen": dict(sorted(Counter(f["decada_origen"] for f in rows
                                                    if f["decada_origen"]).items())),
        "sin_fecha_de_origen": sum(1 for f in rows if not f["decada_origen"]),
    }
    with open(NUMBERS, "w", encoding="utf-8") as f:
        json.dump(numbers, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in numbers.items() if k != "por_decada_de_origen"},
                     ensure_ascii=False))
    print(f"-> {OUTPUT}")


if __name__ == "__main__":
    main()
