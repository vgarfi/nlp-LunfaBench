# Cómo se armaron los 90 términos

Cada etapa lee la salida de la anterior. Acá van las reglas que definen a los
90 y los números que importan para ellos. Los números completos de cada etapa
quedan en `data/interim/` y los principales, en el manifiesto del corpus.

## 1. Candidatos (etapa 01)

| Fuente                           | Qué aporta                                                |
| -------------------------------- | ---------------------------------------------------------- |
| diccionarioargentino.com         | términos, acepción rioplatense, votos y ejemplos         |
| Wiktionary en inglés (kaikki)   | acepciones marcadas por región                            |
| Wikcionario en español (kaikki) | acepciones marcadas por región, con el lunfardo del tango |

Reglas:

- **Votos.** Del diccionario entran los términos cuya mejor definición tiene
  al menos 3 votos netos.
- **Forma.** Solo palabras sueltas, sin siglas, números, símbolos ni memes.
- **Variantes.** Plurales, variantes gráficas y gerundios se fusionan en su
  lema (*curros* en *curro*), salvo que tengan significado propio (*chauchas*
  = poca plata) o que el diccionario los defina distinto (*facho* y *facha*).
- **Pares de género.** Quedan separados: *burra*, *cotorro*, *gato* y *viejo*
  son términos aparte de su femenino o masculino.
- **Nombres propios.** Los posibles nombres propios quedan marcados y no
  entran al sorteo.

## 2. Capa propuesta (etapa 02)

Cada acepción, en kaikki (glosas en inglés) y en Wikcionario (en español), se
ubica en una región según sus marcas:

- **objetivo:** Argentina, Río de la Plata, lunfardo;
- **competidora:** España, México;
- **amplia:** América, Sudamérica, Cono Sur (se asume que también se usa acá);
- **otra:** otros países;
- **general:** sin marca.

| Capa                  | Regla                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------ |
| falso_amigo           | alguna fuente tiene una acepción de España o México que no se usa acá y con otra glosa |
| polisemico_interno    | sin competidoras, pero con otras acepciones que se usan acá, con otra glosa               |
| lunfardo_sin_homonimo | solo acepciones de la variedad objetivo (y a lo sumo de otras regiones)                    |

Detalles:

- Las glosas solo se comparan dentro de la misma fuente (Jaccard ≥ 0,5),
  porque están en idiomas distintos.
- Las acepciones obsoletas no cuentan, salvo las rioplatenses: el lunfardo
  desusado es el del tango.
- Si ninguna fuente tiene la acepción rioplatense, sale del diccionario
  colaborativo. En ese caso una sola acepción general no alcanza para marcar
  polisemia, porque no se puede saber si es la misma. Por eso términos como
  *gira* salen sin homónimo aunque existan en el español general.

La anotación del grupo sobre los 90 mide cuánto acierta el filtro.

## 3. Controles (etapa 02b)

Un control es una palabra del español general que significa lo mismo acá, en
España y en México. Sale de wordfreq y cumple todo esto:

- es lema en kaikki o Wikcionario, sin acepciones vigentes marcadas para el
  Río de la Plata, España, México o Latinoamérica;
- no está en el diccionario colaborativo ni entre los candidatos;
- es sustantivo, verbo, adjetivo o adverbio, sin acepciones vulgares ni de
  jerga;
- no es una forma flexionada, un homógrafo de nombre propio, un préstamo del
  inglés, un tecnicismo ni una grafía obsoleta.

A cada falso amigo candidato se le buscan hasta 3 controles con Zipf a ±0,25
y largo a ±1 letra, prefiriendo la misma categoría gramatical. Los 15
controles de los 90 se sortean entre todos ellos, así que no están emparejados
uno a uno con los 40 falsos amigos del curado: 10 lo están con alguno y 5 no.
El equilibrio es por grupo (Zipf mediano 4,40 contra 4,29; ver `eda.md`).

## 4. Artistas (etapa 03a)

Entra un artista si su origen está a nivel de ciudad en el Gran Buenos Aires:
la ciudad o alguno de los 24 partidos del conurbano. El origen sale de:

- Wikidata: lugar de nacimiento (P19) de personas con ocupación musical y
  lugar de formación (P740) de grupos;
- MusicBrainz: área o área de origen, filtradas por ID.

Un artista de Wikidata y uno de MusicBrainz se unen solo por el ID de
MusicBrainz, nunca por el nombre. Gardel entra aparte, por `artistas_extra` en
`config.yaml`.

## 5. Contextos (etapa 03b, muestra piloto)

1. **Artistas.** 63 con página en Genius: Gardel y 62 sorteados con semilla
   13, hasta 20 por época de nacimiento o formación (antes de 1930, 1930 a
   1969, desde 1970 y sin fecha).
2. **Canciones.** Las 3 más populares de cada uno, con todos los artistas
   principales de Buenos Aires: 143 canciones. 29 no estaban en español, así
   que los términos se buscaron en **114 canciones de 46 artistas**.
3. **Búsqueda.** Todos los candidatos y controles a la vez:
   - sin distinguir tildes ni mayúsculas;
   - con sus plurales, variantes y conjugaciones.
4. **Fragmentos.** Cada aparición es un fragmento de hasta 25 palabras, con el
   término una sola vez y sin repetir estribillos. Los saltos de verso se
   marcan con " / ".

Las letras nunca se guardan: quedan solo los fragmentos y, por canción, el
conjunto de palabras distintas.

## 6. Sorteo (etapa 04)

Se sortea exactamente la cuota de cada capa (40 falsos amigos, 20 sin
homónimo, 15 polisémicos y 15 controles), con semilla 13, entre los términos
con fragmentos de al menos 8 palabras. Tienen prioridad los que aparecen en
dos canciones distintas. Quedan afuera:

- las 500 palabras más frecuentes del español (*no*, *dar*, *hacer*);
- los posibles nombres propios;
- los falsos amigos cuya acepción rioplatense también se usa en España
  (*facha*).

Cada término lleva dos fragmentos, A y B, de canciones distintas cuando se
puede, para que el grupo elija el que usa la acepción.

**Fragmentos con otra palabra.** A veces la forma de la letra es otra palabra:
*temo* es de *temer* y no de *temar*, y *papá* no es *papa*. Si ni A ni B
traen el término:

- se eligen otros fragmentos del mismo término;
- si no hay, entra el siguiente de su capa en el orden del sorteo.

El detalle está en el manifiesto, en `seleccion.reemplazados`.

**Acepción de referencia.** Para cada término se toma, en este orden:

- la primera definición del diccionario colaborativo, salteando las que solo
  anuncian acepciones ("Dos sentidos", en *chamuyo*);
- si no hay, la de Wikcionario;
- si tampoco, la de Wiktionary.

Para los controles, la acepción general.
