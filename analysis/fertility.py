"""Subwords per term in each tokenizer: how many pieces each term produces in
its dictionary form. pipeline.freeze uses it to store the fertility of the
curated terms; analysis.eda also measures the form that appears in the lyric.

The word is measured in isolation, as it appears inside a text: with a
leading space in RoBERTa-style BPE tokenizers (without the space the count is
different and misleadingly better) and lowercased in the uncased ones. The
terms are the candidates of stage 02 with their proposed layer and the main
controls paired in frequency and length.

Needs access to huggingface.co to download the tokenizers (only the
tokenizers, not the weights).

Usage: python -m analysis.fertility
Output: data/interim/fertilidad_por_termino.csv
"""

import csv
import os
import statistics
from collections import defaultdict

from transformers import AutoTokenizer

from pipeline import common
from pipeline import stage02_layer as s02
from pipeline import stage02b_controls as s02b

OUTPUT = os.path.join(common.DATA_INTERIM, "fertilidad_por_termino.csv")

# The three evaluated encoders, and mBERT only as a reference.
MODELS = {
    "robertuito": {"hf": "pysentimiento/robertuito-base-uncased", "bpe": True, "lowercase": True,
                   "label": "RoBERTuito (tweets from several countries)"},
    "beto": {"hf": "dccuchile/bert-base-spanish-wwm-cased", "bpe": False, "lowercase": False,
             "label": "BETO (Wikipedia and OPUS)"},
    # The official repository (PlanTL-GOB-ES/roberta-base-bne) was emptied in
    # July 2025. Fine-tuning does not change the tokenizer: the one of this
    # derivative (by the BETO authors) is identical to the one of the copies
    # of the original (50,262 pieces, same tokenizations).
    "roberta_bne": {"hf": "dccuchile/roberta-base-bne-finetuned-ner", "bpe": True,
                    "lowercase": False, "label": "RoBERTa-BNE (.es web)"},
    "mbert": {"hf": "bert-base-multilingual-cased", "bpe": False, "lowercase": False,
              "label": "mBERT (multilingual reference)"},
}


def count_subwords(tok, word, bpe, lowercase):
    text = word.lower() if lowercase else word
    return len(tok.tokenize(" " + text if bpe else text))


def main():
    terms = [(c["term"], c["capa_propuesta"]) for c in common.read_jsonl(s02.OUTPUT)]
    with open(s02b.PAIRINGS, encoding="utf-8") as f:
        terms += [(r["control_principal"], "control_negativo")
                  for r in csv.DictReader(f) if r["control_principal"]]

    tokenizers = {m: AutoTokenizer.from_pretrained(d["hf"]) for m, d in MODELS.items()}
    rows = []
    for term, layer in terms:
        row = {"term": term, "capa": layer}
        for m, d in MODELS.items():
            row[m] = count_subwords(tokenizers[m], term, d["bpe"], d["lowercase"])
        rows.append(row)

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by_layer = defaultdict(list)
    for row in rows:
        by_layer[row["capa"]].append(row)
    for layer, fs in sorted(by_layer.items()):
        print(f"{layer:<24} n={len(fs):<5} " +
              "  ".join(f"{m}={round(statistics.mean(f[m] for f in fs), 2)}" for m in MODELS))
    print(f"-> {OUTPUT}")


if __name__ == "__main__":
    main()
