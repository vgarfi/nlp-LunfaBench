"""Stage 05: the items a speaker from Spain answers (config «hablante»).

--build: picks the 30 items (a seeded draw of the eligible false friends
  and of the other layers), shuffles their order with the same seed and writes, in
  data/annotation/hablante_es/:
  - formulario.csv: what the speaker sees, blind (number, the word as it appears
    in the fragment, fragment with one verse per line, options A-D in each item's fixed order). It is pasted
    into a Google Sheet and pipeline/speaker_form.gs turns it into a Google
    Form.
  - clave.csv: which item each question is and which letter is which option.
    NOT to be shared with the speaker.
--grade RESPONSES: reads the responses exported from the Google Form (CSV)
  and writes clave-graded answers to data/annotation/hablante_es/respuestas.csv
  (one row per question: chosen letter, chosen option, correct or not).

Usage:
    python -m pipeline.stage05_speaker --build
    python -m pipeline.stage05_speaker --grade path/to/responses.csv
"""

import argparse
import csv
import json
import os
import random
import re

from pipeline import common
from pipeline import stage04_curated as s04

OUT_DIR = os.path.join(s04.ANNOTATION_DIR, "hablante_es")
FORM = os.path.join(OUT_DIR, "formulario.csv")
KEY = os.path.join(OUT_DIR, "clave.csv")
GRADED = os.path.join(OUT_DIR, "respuestas.csv")


def pick(items, conf):
    """A seeded draw of the eligible false friends and of each other layer."""
    by_id = {x["source"]["planilla_id"]: x for x in items}
    eligible = [by_id[i] for i in sorted(conf["falsos_amigos_elegibles"])]
    assert all(x["layer"] == "falso_amigo" for x in eligible), "an eligible item is not a false friend"
    rng = random.Random(conf["semilla"])
    chosen = rng.sample(eligible, conf["falsos_amigos_sorteados"])
    for layer, n in conf["por_capa_sorteados"].items():
        pool = sorted((x for x in items if x["layer"] == layer
                       and x["source"]["planilla_id"] not in conf["excluir"]
                       and x["context_source"] == "letra"),
                      key=lambda x: x["source"]["planilla_id"])
        chosen += rng.sample(pool, n)
    rng.shuffle(chosen)
    return chosen


def shown_form(form, cfg):
    """The word as the speaker reads it in the fragment: the capital at the
    start of a verse is lowered there too (config «entrada_modelos»)."""
    if form in cfg["entrada_modelos"]["conservan_mayuscula"]:
        return form
    return form[:1].lower() + form[1:]


def build(cfg):
    items = list(common.read_jsonl(s04.ANNOTATED))
    chosen = pick(items, cfg["hablante"])
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(FORM, "w", newline="", encoding="utf-8") as f, \
            open(KEY, "w", newline="", encoding="utf-8") as k:
        form, key = csv.writer(f), csv.writer(k)
        form.writerow(["n", "palabra", "fragmento", "A", "B", "C", "D"])
        key.writerow(["n", "planilla_id", "termino", "capa", "letra_correcta",
                      "A", "B", "C", "D"])
        for n, x in enumerate(chosen, 1):
            order = x["presentation"]
            form.writerow([n, shown_form(x["form_in_context"], cfg), x["input_text_llm"]]
                          + [x["options"][order[letter]] for letter in "ABCD"])
            key.writerow([n, x["source"]["planilla_id"], x["term"], x["layer"],
                          x["answer_letter"]] + [order[letter] for letter in "ABCD"])
    layers = {}
    for x in chosen:
        layers[x["layer"]] = layers.get(x["layer"], 0) + 1
    print(f"{len(chosen)} items {layers} -> {FORM} (and {KEY})")


def grade(path):
    """One row per question with the letter chosen («A) ...» in the form)."""
    key = {int(r["n"]): r for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    rows = list(csv.reader(open(path, encoding="utf-8")))
    header, answers = rows[0], rows[1:]
    # Question columns start with their number: «12. ¿Qué significa...».
    columns = {int(m.group(1)): i for i, h in enumerate(header)
               if (m := re.match(r"\s*(\d+)\.", h))}
    missing = sorted(set(key) - set(columns))
    if missing:
        raise SystemExit(f"questions not found in the responses file: {missing}")
    out = []
    for r, answer in enumerate(answers, 1):
        for n, i in sorted(columns.items()):
            letter = answer[i].strip()[:1]
            k = key[n]
            out.append({"respuesta": r, "n": n, "planilla_id": k["planilla_id"],
                        "termino": k["termino"], "capa": k["capa"], "letra": letter,
                        "opcion": k.get(letter, ""), "correcta": letter == k["letra_correcta"]})
    with open(GRADED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    right = sum(o["correcta"] for o in out)
    print(json.dumps({"respuestas": len(out), "correctas": right,
                      "eligio_b": sum(o["opcion"] == "b_otra_variedad" for o in out)},
                     ensure_ascii=False))
    print(f"-> {GRADED}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--grade", metavar="RESPONSES")
    args = ap.parse_args()
    cfg = common.load_config()
    if args.build:
        build(cfg)
    if args.grade:
        grade(args.grade)


if __name__ == "__main__":
    main()
