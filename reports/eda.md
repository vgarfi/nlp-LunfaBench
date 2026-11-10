# Análisis exploratorio de los 116

Generado con `python -m analysis.eda` y `python -m analysis.figure_curated` (el
detalle está en `eda_numeros.json`). La capa de cada término es la que decidió
el grupo en la planilla («capa final»). Son los 90 del sorteo (`pipeline.md`)
más 26 que el grupo agregó a mano en la revisión, sobre todo falsos amigos.

## Por capa

| Capa | Términos | Zipf mediano | En wordfreq | Largo mediano | Subwords del término | Subwords en la letra | Con fragmento B |
|---|---|---|---|---|---|---|---|
| Falsos amigos | 42 | 3,90 | 42 | 5 | 1,24 / 1,62 / 1,62 | 1,31 / 1,81 / 1,74 | 17 |
| Sin homónimo | 20 | 2,92 | 18 | 5 | 1,70 / 2,30 / 2,10 | 1,70 / 2,25 / 2,10 | 16 |
| Polisémicos | 37 | 4,19 | 37 | 5 | 1,16 / 1,41 / 1,32 | 1,26 / 1,56 / 1,44 | 34 |
| Controles | 17 | 4,32 | 17 | 5 | 1,12 / 1,24 / 1,24 | 1,12 / 1,24 / 1,24 | 17 |

Subwords promedio en RoBERTuito / BETO / RoBERTa-BNE:
- **del término:** su forma de diccionario (*quemar*);
- **en la letra:** la forma que aparece en el fragmento A (*quemando*), que es
  la que tokeniza el modelo. Es la que va en la Tabla 2 del informe. En los
  polisémicos se calcula sobre 34 términos, porque 3 tienen un fragmento que no
  es de una canción.

**Fuentes de los 99 rioplatenses** (un término puede estar en varias):
- 75 en el diccionario colaborativo;
- 40 en el Wikcionario;
- 4 sin ninguna de las dos: su acepción la redactó el grupo.

Todas las acepciones están en español. Los controles salen de wordfreq.

## Contextos

- **200 fragmentos.** 197 son de letras: 124 canciones de 63 artistas. Los
  otros 3 no son de canciones: dos ejemplos de diccionario (*cargar*, *quemar*)
  y una frase del grupo (*quebrar*). Se cuentan, pero quedan fuera de todas las
  estadísticas de letras.
- **Uno o dos por término.** Hay dos por término, salvo 32 que tienen uno solo:
  los 26 agregados a mano y 6 del sorteo. En 1 término, A y B son de la misma
  canción.
- **Largo:** mediana de 22 palabras, entre 8 y 25.
- **Flexiones:** en 55 fragmentos (28 %) el término aparece flexionado, como
  *quemando* por *quemar*.
- **Otra palabra:** 3 fragmentos traen otra palabra con la misma forma. Quedan
  marcados con `forma_de_otra_palabra`.
- **Figura 1** (`figura_curado.png`): términos de cada capa según la década del
  fragmento A, con el total de cada capa entre paréntesis.
  - 101 de los 113 fragmentos A de letras tienen año según Genius, entre 1910 y
    2020.
  - La fila de polisémicos suma 34 y no 37: los 3 fragmentos que no son de
    canciones no tienen década.
  - Todas las capas tienen fragmentos de varias épocas.

## Lecturas

1. **Los controles no están emparejados en frecuencia con los falsos amigos.**
   Es la limitación más importante del conjunto. Los controles son 17: los 15
   del sorteo y 2 términos que la anotación pasó a español general. Se
   sortearon para emparejarse con un conjunto de falsos amigos que después
   cambió: hoy la capa tiene léxico más marcadamente rioplatense, que es más
   raro, con una mediana de 3,90 contra 4,32 de los controles. Esa diferencia
   de 0,42 en Zipf significa que los controles son unas dos veces y media más
   frecuentes. **Una diferencia de acierto entre esas dos capas no se puede
   atribuir solo al dialecto: hay que controlar la frecuencia**, como
   covariable o emparejando de nuevo.
2. **Rareza de los sin homónimo.**
   - Siguen siendo la capa más rara (Zipf 2,92) y 2 de 20 no están en wordfreq.
   - Si un modelo falla más ahí, puede ser por rareza y no por sesgo.
3. **Épocas.** Todas las capas tienen fragmentos de varias décadas, así que la
   tendencia de canciones recientes contra tangos se puede medir, aunque con
   pocos ítems por década.
4. **Subwords.**
   - En el término aislado casi repiten la frecuencia: correlación de −0,84 con
     el Zipf.
   - La brecha entre tokenizadores se ordena como predice H4: en los sin
     homónimo, RoBERTuito parte en 1,70 subwords contra 2,30 de BETO y 2,10 de
     RoBERTa-BNE. Términos como *guita*, *chabón*, *quilombo*, *yuta* y *bondi*
     son **un solo token en RoBERTuito y más de uno en los otros dos**, que es
     exactamente el efecto que H4 quiere medir.
   - En la forma de la letra la brecha se mantiene (falsos amigos 1,81 en BETO
     contra 1,24 de los controles). Sale de las flexiones y de las mayúsculas
     de comienzo de verso. La comparación principal tiene que controlarlo, y la
     sonda tiene que promediar los subwords del término.

## Limitaciones

- **26 términos agregados a mano.** No pasaron por el filtro: su capa propuesta
  la puso el grupo. Para comparar el filtro con la anotación (Tabla 2 del
  informe) cuentan solo los 90 del sorteo.
- **Acepción del fragmento.** Los dos anotadores eligieron en la planilla, para
  cada uno de los 116 términos, el fragmento que usa la acepción de referencia
  («fragmento final»). En el corpus, `validated_sense: true` marca los 67
  fragmentos A que el grupo puso a mano en las revisiones; los 49 que quedaron
  del pipeline siguen en `false` y los validó la anotación.
- **Fragmentos buscados a mano.** Para 11 términos cuyo fragmento no ilustraba
  la acepción rioplatense, el grupo buscó otro a mano. En 8 apareció en una
  letra; para *cargar*, *quemar* y *quebrar* no apareció en ninguna, y llevan
  los fragmentos sin canción de arriba. *Ciego*, *muerto*, *dormir* y *muñeca*,
  hoy polisémicos, conservan el fragmento del pipeline que eligieron los
  anotadores.
- **Acepción competidora.** La de cada falso amigo (opción b) la escribieron
  los anotadores en la planilla. Donde escribieron sentidos distintos, el grupo
  eligió uno (12 términos, en `acepcion_competidora_elegida.csv`). En 13 el DLE
  no tiene una acepción marcada de España o México (*macana*, *pendejo*,
  *boliche*, *acabar*, *gomas*, *cheto*, *piña*, *chota*, *pava*, *banda*,
  *pucha*, *bardo* y *colectivo*): ahí la competidora es un sentido general,
  no uno regional.
- **Pocos artistas.** Cuatro artistas (Edmundo Rivero, Tita Merello, Zaramay y
  Dillom) aportan 65 de los 197 fragmentos de letras (33 %). El estilo de esos
  artistas pesa en los resultados.
- **Origen de 28 fragmentos verificado a mano.** Una parte de los artistas no
  pasó por la verificación automática de origen con Wikidata y MusicBrainz: su
  procedencia porteña la chequeó el grupo, y esos fragmentos quedan marcados
  con `origin_source: verificacion_manual_grupo`.
- **Cuatro acepciones sin respaldo de diccionario.** *viste*, *correr*, *bola*
  y *cartera* no tienen esa acepción en el Wikcionario ni en
  diccionarioargentino.com, así que la redactó el grupo.
- **Año tomado de Genius.** Para tangos suele ser el de una reedición, así que
  las décadas de la Figura 1 son aproximadas.
- **Tokenizador de RoBERTa-BNE.** El repositorio oficial se vació en 2025. Los
  subwords se contaron con una copia idéntica del tokenizador.

## Decisiones pendientes sobre la entrada de los modelos

- **Separador de versos.** Hoy es `" / "`, y el codebook dice que se quitan los
  saltos.
- **Mayúsculas de comienzo de verso.** Al unir los versos, la primera palabra
  de cada uno queda con mayúscula en medio del fragmento (*Cargar*), y los
  modelos que distinguen mayúsculas la parten en más subwords.
- **Emparejamiento de los controles.** Ver la lectura 1: hay que decidir si se
  vuelven a sortear los controles para emparejarlos con los falsos amigos
  actuales, o si se controla la frecuencia en el análisis.
