# %% [markdown]
# # LunfaBench - Extractor de fragmentos cortos desde Genius
#
# Este notebook busca canciones en Genius, localiza las lineas donde aparece
# cada termino, y guarda SOLO un fragmento corto de contexto (por defecto:
# la linea encontrada + 1 linea antes/despues, recortado a <=25 palabras).
#
# **La letra completa que baja la API NUNCA se escribe a disco ni se
# imprime completa: se usa en memoria y se descarta.** No corras nada que
# imprima `full_lyrics` completo, ni lo pegues en el chat/commits.
#
# Requisitos antes de correr:
# 1. `pip install lyricsgenius`
# 2. Crear un cliente en https://genius.com/api-clients y copiar el
#    "Client Access Token".
# 3. Ponerlo en un archivo `.env` en la raiz del repo (NUNCA en el codigo ni
#    commiteado; `.env` ya esta en `.gitignore`):
#    `GENIUS_TOKEN=tu_token_aca`
#    O alternativamente exportarlo como variable de entorno:
#    `export GENIUS_TOKEN="tu_token_aca"` (Mac/Linux)
#
# Correr las celdas en orden (Cell 1 a 1 en VS Code / Jupyter).

# %%
import os
import re
import csv
import json
from datetime import datetime

try:
    import lyricsgenius
except ImportError:
    raise SystemExit("Falta instalar la libreria. Corri: pip install lyricsgenius")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMINOS_CSV = os.path.join(REPO_ROOT, "data", "lunfabench_terminos_v0.csv")
BUSQUEDAS_CSV = os.path.join(REPO_ROOT, "data", "busquedas.csv")
FRAGMENTS_DIR = os.path.join(REPO_ROOT, "data", "fragments")
FRAGMENTS_OUT = os.path.join(FRAGMENTS_DIR, "fragments_batch.jsonl")


def load_dotenv(path=os.path.join(REPO_ROOT, ".env")):
    """Carga variables de un .env local (sin dependencias externas). No pisa
    variables ya presentes en el entorno. El .env nunca se commitea
    (esta en .gitignore)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

MAX_WORDS = 25  # tope del brief para cada fragmento
CONTEXT_LINES = 1  # cuantas lineas antes/despues de la linea con el termino

# %% [markdown]
# ## Cliente de Genius
# Requiere `GENIUS_TOKEN` en el entorno. Correr una sola vez por sesion.

# %%
def get_client():
    token = os.environ.get("GENIUS_TOKEN")
    if not token:
        raise SystemExit(
            "No encontre la variable de entorno GENIUS_TOKEN. "
            "Configurala antes de correr esta celda (ver instrucciones arriba)."
        )
    return lyricsgenius.Genius(
        token,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)"],
        remove_section_headers=True,
        timeout=15,
    )


genius_client = get_client()
print("Cliente de Genius listo.")

# %% [markdown]
# ## Funciones core
# `extract_fragment` recibe la letra completa SOLO en memoria y devuelve un
# fragmento corto. Nunca retorna ni persiste la letra completa.

# %%
def extract_fragment(full_lyrics: str, term: str, context_lines: int = CONTEXT_LINES):
    lines = [l for l in full_lyrics.split("\n") if l.strip()]
    pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)

    for i, line in enumerate(lines):
        if pattern.search(line):
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            fragment_lines = lines[start:end]
            fragment = " / ".join(fragment_lines).strip()

            words = fragment.split()
            if len(words) > MAX_WORDS:
                idx = next((j for j, w in enumerate(words) if pattern.search(w)), len(words) // 2)
                lo = max(0, idx - MAX_WORDS // 2)
                hi = min(len(words), lo + MAX_WORDS)
                fragment = " ".join(words[lo:hi])

            return fragment

    return None  # el termino no aparecio en esta cancion


# Genius mete homoglifos cirilicos sueltos en muchas letras. Un solo caracter
# de estos rompe la tokenizacion en subwords, que es justo lo que mide H4, asi
# que se normalizan en vez de descartar la fuente entera.
HOMOGLIFOS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "і": "i", "һ": "h", "Α": "A",
    "Ε": "E", "Ο": "O", "Р": "P", "С": "C", "Х": "X",
}


def normalizar_homoglifos(texto: str) -> str:
    return "".join(HOMOGLIFOS.get(ch, ch) for ch in texto)


def validate_source(song, full_lyrics):
    """Filtros aprendidos a los golpes contra la busqueda difusa de Genius.
    Devuelve None si la fuente sirve, o el motivo de descarte."""
    # Las paginas que no son canciones (calendarios editoriales, indices de
    # transcripciones) terminan en -annotated en vez de -lyrics.
    if song.url.endswith("-annotated"):
        return "no es una cancion (pagina -annotated de Genius)"

    # Algunas transcripciones viejas tienen TODOS los acentos borrados
    # ("mas" por "mas", "sabado" por "sabado"): arruinan la cita textual.
    lower = full_lyrics.lower()
    accent_suspects = sum(1 for s in (" mas ", " asi ", " aqui ", " tambien ") if s in lower)
    if accent_suspects >= 2 and not any(c in full_lyrics for c in "áéíóúñÁÉÍÓÚÑ"):
        return "transcripcion con acentos corruptos"

    # Anti falso positivo de idioma (portugues sobre todo).
    padded = " " + lower + " "
    es_hits = sum(padded.count(m) for m in (" que ", " para ", " con ", " pero ", " no "))
    pt_hits = sum(padded.count(m) for m in (" nao ", " voce ", " pra ", " muito "))
    if es_hits <= 5 or pt_hits >= 3:
        return "la letra no parece espanol rioplatense"

    return None


def build_item(term: str, artist_query: str, song_query: str, item_id: str = "", year=None):
    song = genius_client.search_song(song_query, artist_query)
    if song is None and artist_query:
        # Genius suele indexar tangos viejos bajo el interprete, no el autor/compositor.
        # Reintenta solo por titulo si la combinacion con artista no matcheo.
        song = genius_client.search_song(song_query)
    if song is None:
        print(f"  [!] No encontre '{song_query}' de '{artist_query}' en Genius")
        return None

    full_lyrics = normalizar_homoglifos(song.lyrics)  # queda SOLO en esta variable local

    rechazo = validate_source(song, full_lyrics)
    if rechazo:
        del full_lyrics
        print(f"  [!] DESCARTADA '{song.title}' de '{song.artist}': {rechazo}")
        return None

    fragment = extract_fragment(full_lyrics, term)
    del full_lyrics  # se descarta explicitamente, no se persiste

    if fragment is None:
        print(f"  [!] El termino '{term}' no aparecio en '{song.title}'")
        return None

    return {
        "id": item_id or f"LB-{term}-{datetime.now().strftime('%H%M%S')}",
        "term": term,
        "context": fragment,
        "source": {
            "song": song.title,
            "artist": song.artist,
            # `year` es el ano curado a mano. Para tangos, Genius devuelve la fecha
            # de ESTA grabacion (a menudo un cover posterior), no la de composicion,
            # asi que se guarda aparte para poder contrastar, no para pisar el curado.
            "year": year or None,
            "genius_release": song.to_dict().get("release_date_for_display"),
            "url": song.url,
        },
    }


print("Funciones definidas.")

# %% [markdown]
# ## Prueba individual
# Util para probar un termino suelto antes de tirar el batch completo.
# Cambia las variables y corre la celda; no hace falta editar el resto del
# archivo.

# %%
TEST_TERM = "facha"
TEST_ARTIST = ""
TEST_SONG = ""

if TEST_ARTIST and TEST_SONG:
    item = build_item(TEST_TERM, TEST_ARTIST, TEST_SONG)
    if item:
        print(json.dumps(item, ensure_ascii=False, indent=2))
else:
    print("Completa TEST_ARTIST y TEST_SONG arriba para probar un termino suelto.")

# %% [markdown]
# ## Modo batch
# Lee `data/busquedas.csv` (columnas: `id,term,layer,stratum,artist,song,year`)
# y busca cada fila en Genius. Las filas con `artist`/`song` vacios se
# saltean (todavia no se eligio la cancion).

# %%
def run_batch(busquedas_csv=BUSQUEDAS_CSV):
    results = []
    skipped = []
    not_found = []

    with open(busquedas_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = row["term"].strip()
            artist = row.get("artist", "").strip()
            song = row.get("song", "").strip()
            item_id = row.get("id", "").strip()
            year = row.get("year", "").strip() or None

            if not artist or not song:
                skipped.append(item_id or term)
                continue

            print(f"Buscando: '{term}' en '{song}' de '{artist}'...")
            item = build_item(term, artist, song, item_id, year)
            if item:
                results.append(item)
            else:
                not_found.append(item_id or term)

    print(f"\nListo: {len(results)} encontrados, {len(not_found)} sin match, {len(skipped)} sin cancion elegida.")
    return results, skipped, not_found


results, skipped, not_found = run_batch()

# %% [markdown]
# ## Guardar resultados crudos
# Se guarda el batch como JSONL en `data/fragments/`. Solo fragmentos
# cortos + metadata de fuente, nunca letras completas.

# %%
os.makedirs(FRAGMENTS_DIR, exist_ok=True)
with open(FRAGMENTS_OUT, "w", encoding="utf-8") as f:
    for item in results:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

print(f"Guardado en {FRAGMENTS_OUT}")

# %% [markdown]
# ## Mergear resultados en el CSV principal
# Actualiza `context_fragment`, `source_song`, `source_artist`,
# `source_year`, `source_url` en `data/lunfabench_terminos_v0.csv` para las
# filas cuyo `id` aparece en los resultados. No pisa filas que ya tenian
# fragmento cargado, salvo que se ponga `OVERWRITE = True`.

# %%
OVERWRITE = False

with open(TERMINOS_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

by_id = {item["id"]: item for item in results}
updated, already_had = 0, 0

for row in rows:
    item = by_id.get(row["id"])
    if not item:
        continue
    if row.get("context_fragment") and not OVERWRITE:
        already_had += 1
        continue
    row["context_fragment"] = item["context"]
    row["source_song"] = item["source"]["song"]
    row["source_artist"] = item["source"]["artist"]
    row["source_year"] = item["source"]["year"] or ""
    row["source_url"] = item["source"]["url"]
    updated += 1

with open(TERMINOS_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"CSV actualizado: {updated} filas nuevas, {already_had} ya tenian fragmento (no tocadas).")

# %% [markdown]
# ## Pendientes
# Terminos que todavia necesitan cancion elegida o una nueva busqueda.

# %%
still_missing = [r["id"] for r in rows if not r.get("context_fragment")]
print(f"Faltan {len(still_missing)} terminos: {still_missing}")
