# LunfaBench

Benchmark de sesgo dialectal ante léxico rioplatense (TP de NLP, ITBA).
Integrantes: Tomás Borda, Valentin Augusto Garfi y Juan Ignacio Cantarella.

Un pipeline arma los ítems a partir de diccionarios y letras de canciones de
artistas de Buenos Aires: 90 términos en cuatro capas (40 falsos amigos, 20
sin homónimo, 15 polisémicos y 15 controles), cada uno con fragmentos reales
de letras. Esos 90 quedan congelados en `data/curated/`.

Cómo se armaron: `reports/pipeline.md`. Análisis exploratorio:
`reports/eda.md`.

## Estructura

```
config.yaml            parámetros de todo el pipeline (umbrales, semillas, cuotas)
requirements.txt       dependencias de Python
.env                   token de Genius (no va a git)

pipeline/              el pipeline: una etapa por archivo (código en inglés)
  stage01_candidates.py    candidatos de los tres diccionarios
  stage02_layer.py         capa propuesta: falso amigo, polisémico o sin homónimo
  stage02b_controls.py     controles de español general, emparejados en frecuencia
  stage03a_artists.py      artistas de Buenos Aires y el conurbano
  stage03b_contexts.py     fragmentos de letras (muestra piloto)
  stage04_curated.py       sorteo de los 90, planilla de anotación y evaluación
  freeze.py                copia los 90 a data/curated/ con su procedencia
  source_*.py              acceso a cada fuente: diccionarioargentino.com,
                           kaikki (Wiktionary), Wikcionario, Wikidata,
                           MusicBrainz y Genius
  regions.py               decide la región de cada acepción por sus marcas
  common.py                utilidades: rutas, normalización, caché HTTP, JSONL

analysis/
  fertility.py           subwords por término en cada tokenizador
  eda.py                 números del análisis exploratorio de los 90
  figure_curated.py      Figura 1 del informe

data/
  curated/               EL CORPUS CONGELADO (ver abajo)
  annotation/            la planilla de anotación y su clave
    curado_planilla.xlsx   planilla de anotación de los 90, para compartir
    curado_clave.csv       capa propuesta por el filtro: NO se comparte
  raw/                   descargas y cachés de las fuentes (1,1 GB, no va a git)
  interim/               salidas intermedias y números de cada etapa (no va a git)

data/lunfabench_terminos_v0.csv, data/busquedas.csv, data/fragments/, scripts/
                       primera versión, armada a mano; el pipeline no la usa

reports/
  pipeline.md            cómo se armaron los 90: las reglas de cada etapa
  eda.md, eda_numeros.json  análisis exploratorio de los 90
  figura_curado.png      Figura 1 del informe
```

## El corpus congelado

Son los tres archivos de `data/curated/`:

| Archivo | Qué tiene |
|---|---|
| `curado.jsonl` | Los 90 términos, uno por línea. |
| `manifiesto.json` | Cómo se armó y cómo verificarlo. |
| `config.yaml` | Copia de la configuración con la que se congeló. |

Cada término de `curado.jsonl` tiene:
- **capa:** la propuesta por el filtro y el motivo;
- **acepción de referencia:** con su fuente y enlace;
- **fragmentos A y B:** de hasta 25 palabras, con canción, artista, origen,
  año y la forma en que aparece el término en la letra;
- **frecuencia y subwords:** el Zipf y los subwords en cada tokenizador;
- **procedencia:** las definiciones del diccionario colaborativo y las
  acepciones de Wiktionary y Wikcionario con sus IDs. Para los controles, los
  falsos amigos candidatos con los que se emparejan (no siempre uno de los
  40).

El manifiesto guarda:
- versión y fecha de cada fuente;
- semillas y cuotas;
- números del embudo y del piloto de letras;
- términos reemplazados en el sorteo;
- hash SHA-256 de cada archivo, incluidos la planilla y la clave de
  `data/annotation/`, para comprobar que corresponden a este corpus.

**Qué no es parte del corpus.** Las letras completas nunca se guardan: solo
los fragmentos. Para usar el corpus no hacen falta `data/raw/` ni
`data/interim/`, pero para regenerar este mismo corpus hace falta `data/raw/`
(ver [Cómo se congela](#cómo-se-congela)).

**Anotación ciega.** La capa que propuso el filtro aparece en
`data/curated/`, en `curado_clave.csv` y en `reports/`. Quien anota no los
abre hasta terminar la planilla.

## Cómo se usa

Análisis exploratorio (sale de `data/curated/`):

```
python -m analysis.eda
python -m analysis.figure_curated
```

Cuando el grupo termina la planilla:

```
python -m pipeline.stage04_curated --evaluate data/annotation/curado_planilla.xlsx
```

Eso deja el acuerdo del filtro y entre anotadores en
`reports/04_curado_numeros.json`, y los 90 ítems con su capa y fragmento
finales en `data/curated/curado_anotado.jsonl`.

## Cómo se congela

Congelar es correr el pipeline completo una vez y guardar el resultado en
`data/curated/`. A partir de ahí, la anotación, el EDA y los experimentos
usan esa copia, y el pipeline no se vuelve a correr.

Los comandos, en orden (unos 6 minutos):

```
python -m pipeline.stage01_candidates --cache-only
python -m pipeline.stage02_layer
python -m pipeline.stage02b_controls
python -m pipeline.stage03a_artists
python -m pipeline.stage03b_contexts --step genius --cache-only
python -m pipeline.stage03b_contexts --step songs
python -m pipeline.stage03b_contexts --step lyrics
python -m analysis.fertility
python -m pipeline.stage04_curated --select
python -m pipeline.freeze
```

`stage04_curated --select` sortea los 90 y escribe la planilla y la clave en
`data/annotation/`, y `freeze` escribe `data/curated/`. Los dos pisan lo que
haya: antes de correrlos hay que guardar una copia de las dos carpetas, sobre
todo si el grupo ya anotó la planilla.

**Cuándo sale el mismo corpus.** Los sorteos usan las semillas fijas de
`config.yaml`, así que con las mismas entradas sale el mismo `curado.jsonl`,
byte a byte. Las entradas son tres:
- **`data/raw/`:** las descargas y cachés del congelado (los tres
  diccionarios, Wikidata, MusicBrainz y la API de Genius). No va a git, así
  que hay que pasarla aparte. Sin esa carpeta hay que sacar `--cache-only` de
  los comandos, y el pipeline baja las fuentes como están hoy: como cambian,
  puede salir otro corpus.
- **Las letras:** el paso de letras las vuelve a bajar de Genius, porque nunca
  se guardan, y necesita el token en `.env`. Si Genius corrigió o borró una
  canción, puede cambiar un fragmento.
- **Las versiones:** el Zipf y los subwords dependen de wordfreq y de los
  tokenizadores, que se bajan de Hugging Face. El corpus actual sale con
  Python 3.13, wordfreq 3.1.1 y transformers 5.17.0.

**Cómo comprobarlo.** Salió el mismo corpus si el SHA-256 del `curado.jsonl`
nuevo coincide con el del manifiesto de la copia. Si no coincide, es otro
corpus, y la anotación y el EDA se rehacen sobre él. La planilla y el
manifiesto no sirven para comparar: guardan la fecha de la corrida y cambian
aunque el contenido sea el mismo.
