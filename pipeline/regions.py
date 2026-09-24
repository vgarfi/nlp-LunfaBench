"""Where each sense is used, according to the regional marks of Wiktionary.

Works for both sources (English Wiktionary and Spanish Wikcionario): each one
has its block in config.yaml (variedades and variedades_wikcionario) with the
labels that count as target variety, competitors and broad regions.
"""


def group_marks(sense, group):
    """Labels of the group (target, competitors or broad regions) present in
    the sense, looked up in tags, categories and free-text raw_tags."""
    found = [t for t in sense["tags"] if t in group["tags"]]
    found += [c for c in sense["categorias_variedad"] if c in group["categorias"]]
    found += [r for r in sense["raw_tags"]
              if any(t.lower() in r.lower() for t in group["texto"])]
    return found


def sense_region(sense, varieties):
    """Classifies a sense by where it is used:
    - objetivo: marked for the target variety (even if it is also marked for
      a competitor, like facha = looks, Rioplatense and Spain);
    - amplia: marked for a region that includes the target;
    - competidora: marked for a competitor and for none of the above;
    - otra: marked only for other regions (Chile, Andalusia...);
    - general: no regional mark.
    Returns (region, labels that justify it)."""
    for region, group in (("objetivo", "objetivo"), ("amplia", "amplias"),
                          ("competidora", "competidoras")):
        found = group_marks(sense, varieties[group])
        if found:
            return region, found
    prefixes = tuple(varieties.get("prefijos_no_regionales", []))
    others = [c for c in sense["categorias_variedad"]
              if c not in varieties["categorias_no_regionales"]
              and not (prefixes and c.startswith(prefixes))]
    if others:
        return "otra", others
    return "general", []
