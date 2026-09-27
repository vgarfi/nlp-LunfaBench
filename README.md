# LunfaBench

Benchmark de sesgo dialectal ante léxico rioplatense. TP de NLP, ITBA.
Tomás Borda, Valentin Augusto Garfi y Juan Ignacio Cantarella.

Los modelos de lenguaje aprenden un español dominado por las variedades
peninsular y mexicana. Queremos medir qué hacen ante una palabra que acá
significa una cosa y allá otra, como *curro*: no solo si se equivocan, sino si
sus errores caen siempre del mismo lado.

Son **90 términos**, cada uno con su acepción rioplatense y un fragmento
real de alguna letra de canción de artistas de Buenos Aires. Quedan congelados en
`data/curated/`.

| Capa | Qué la define | Ejemplo |
|---|---|---|
| Falso amigo (40) | Existe en las dos variedades, con significados distintos. | *curro*: acá negocio turbio; en España, trabajo. |
| Sin homónimo (20) | Lunfardo puro: no existe con otro sentido afuera. | *yuta* (policía), *guita* (dinero). |
| Polisémico (15) | Varias acepciones, todas usadas acá. | *careta*: máscara, y también persona hipócrita. |
| Control (15) | Español general: significa lo mismo en todos lados. | *ruido*, *cielo*. Línea de base. |

## Un término del conjunto

```json
{
  "id": "CUR-022",
  "term": "curro",
  "capa_propuesta": "falso_amigo",
  "acepcion_de_referencia": "Situación arreglada previamente, generalmente de manera injusta y/o inmoral.",
  "fuente_acepcion": "https://www.diccionarioargentino.com/term/curro",
  "principal": {
    "forma_en_letra": "curro",
    "context": "dealer' en lo' burro' (Uh) / Aprovechen el momento y saquen provecho al curro (Uh, uh-uh) / Ya tú sabe', canto envido",
    "source": {
      "song": "Freestyle Session #14 “LOS INTOCABLES”",
      "artist": "Zaramay",
      "artist_origin": "Ciudad de General San Martín",
      "origin_source": "wikidata:P19",
      "genius_release_year": 2021,
      "url": "https://genius.com/Zaramay-and-nahuel-the-coach-freestyle-session-14-los-intocables-lyrics"
    },
    "pipeline": { "validated_sense": true }
  },
  "alternativo": "…mismo formato, de otra canción",
  "zipf": 3.48,
  "largo": 5,
  "subwords": { "robertuito": 1, "beto": 2, "roberta_bne": 1, "mbert": 2 }
}
```

Los fragmentos son de 8 a 25 palabras y los saltos de verso se marcan con
`" / "`. **Las letras completas nunca se guardan**: se procesan en memoria y en
disco queda solo el fragmento con su fuente. `subwords` es en cuántos pedazos
parte el término cada tokenizador, y `zipf` su frecuencia en español.

## Estructura

```
pipeline/     una etapa por archivo: candidatos, capa, controles, artistas,
              contextos, sorteo y congelado. source_*.py accede a cada fuente.
analysis/     eda.py, fertility.py y figure_curated.py
data/curated/ el corpus: curado.jsonl, manifiesto.json, config.yaml
data/annotation/  curado_planilla.xlsx (se comparte) y curado_clave.csv (no)
data/raw/, data/interim/   descargas y salidas intermedias (no van a git)
reports/      pipeline.md, eda.md, figura_curado.png e informe de la entrega
config.yaml   umbrales, semillas y cuotas
.env          token de Genius (no va a git)
```

Cómo se armaron los 90: `reports/pipeline.md`. Análisis exploratorio:
`reports/eda.md`.