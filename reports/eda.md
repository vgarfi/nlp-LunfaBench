# Análisis exploratorio de los 90

Generado con `python -m analysis.eda` y `python -m analysis.figure_curated` (el
detalle está en `eda_numeros.json`). La capa de cada término es la que propone
el filtro; la del grupo sale de la planilla. Cómo se armaron los 90:
`pipeline.md`.

## Por capa

| Capa | Términos | Zipf mediano | En wordfreq | Largo mediano | Subwords del término | Subwords en la letra | Con fragmento B |
|---|---|---|---|---|---|---|---|
| Falsos amigos | 40 | 3,81 | 40 | 5 | 1,27 / 1,57 / 1,52 | 1,35 / 1,75 / 1,62 | 40 |
| Sin homónimo | 20 | 3,05 | 18 | 5 | 1,65 / 2,20 / 2,00 | 1,65 / 2,15 / 2,00 | 16 |
| Polisémicos | 15 | 3,99 | 15 | 6 | 1,13 / 1,40 / 1,40 | 1,13 / 1,53 / 1,47 | 14 |
| Controles | 15 | 4,40 | 15 | 5 | 1,13 / 1,13 / 1,13 | 1,07 / 1,13 / 1,13 | 15 |

Subwords promedio en RoBERTuito / BETO / RoBERTa-BNE:
- **del término:** su forma de diccionario (*quemar*);
- **en la letra:** la forma que aparece en el fragmento A (*quemando*), que es
  la que tokeniza el modelo. Es la que va en la Tabla 2 del informe.

**Fuentes de los 75 rioplatenses** (un término puede estar en varias):
- 55 en el diccionario colaborativo;
- 39 en el Wikcionario.

Todas las acepciones están en español. Los controles salen de wordfreq.

## Contextos

- **175 fragmentos** de 97 canciones de 47 artistas. Hay dos por término, salvo
  5 términos que tienen uno solo. En 1 término, A y B son de la misma canción.
- **Largo:** mediana de 21 palabras, entre 8 y 25.
- **Flexiones:** en 52 fragmentos (30 %) el término aparece flexionado, como
  *quemando* por *quemar*.
- **Otra palabra:** en 3 términos, uno de los dos fragmentos trae otra palabra
  con la misma forma. Quedan marcados con `forma_de_otra_palabra` y el grupo
  elige el otro.
- **Figura 1** (`figura_curado.png`): términos de cada capa según la década del
  fragmento A, con el total de cada capa entre paréntesis.
  - 84 de los 90 fragmentos A tienen año según Genius, entre 1910 y 2020.
  - Todas las capas tienen fragmentos de varias épocas.

## Lecturas

1. **Los controles no están emparejados en frecuencia con los falsos amigos.**
   Es la limitación más importante del conjunto. Los 15 controles se sortearon
   para emparejarse con un conjunto de falsos amigos que después cambió: hoy la
   capa tiene léxico más marcadamente rioplatense, que es más raro, con una
   mediana de 3,81 contra 4,40 de los controles. Esa diferencia de 0,59 en Zipf
   significa que los controles son unas cuatro veces más frecuentes. **Una
   diferencia de acierto entre esas dos capas no se puede atribuir solo al
   dialecto: hay que controlar la frecuencia**, como covariable o emparejando
   de nuevo.
2. **Rareza de los sin homónimo.**
   - Siguen siendo la capa más rara (Zipf 3,05) y 2 de 20 no están en wordfreq.
   - Si un modelo falla más ahí, puede ser por rareza y no por sesgo.
3. **Épocas.** Todas las capas tienen fragmentos de varias décadas, así que la
   tendencia de canciones recientes contra tangos se puede medir, aunque con
   pocos ítems por década.
4. **Subwords.**
   - En el término aislado casi repiten la frecuencia: correlación de −0,85 con
     el Zipf.
   - La brecha entre tokenizadores se ordena como predice H4: en los sin
     homónimo, RoBERTuito parte en 1,65 subwords contra 2,20 de BETO y 2,00 de
     RoBERTa-BNE. Términos como *guita*, *chabón*, *quilombo*, *careta* y
     *yuta* son **un solo token en RoBERTuito y dos o tres en los otros dos**,
     que es exactamente el efecto que H4 quiere medir.
   - En la forma de la letra la brecha se mantiene (falsos amigos 1,75 en BETO
     contra 1,13 de los controles). Sale de las flexiones y de las mayúsculas
     de comienzo de verso. La comparación principal tiene que controlarlo, y la
     sonda tiene que promediar los subwords del término.

## Limitaciones

- **Capa propuesta.** Los números por capa usan la capa del filtro. Se
  recalculan con la capa anotada.
- **Acepción del fragmento.** 29 términos tienen el sentido verificado a mano
  (`validated_sense: true`). Los otros conservan `validated_sense: false`: que
  el término esté en la letra no asegura que use la acepción de referencia. Lo
  decide el grupo al elegir entre el fragmento A y el B.
- **13 términos con fragmentos que no ilustran su acepción.** Se buscaron en
  765 canciones de 72 artistas y su acepción rioplatense no aparece en ninguna,
  porque en las letras esas palabras se usan en su sentido común. Son
  *cargar*, *vacío*, *quemar*, *duro*, *ciego*, *quebrar* y *salado* entre los
  falsos amigos, y *muerto*, *dormir*, *fumar*, *plato*, *muñeca* y *atado*
  entre los polisémicos. Quedan como candidatos a reemplazo si aparece
  material, y conviene tenerlos identificados al leer los resultados por capa.
- **Pocos artistas.** Cuatro artistas (Edmundo Rivero, Zaramay, Tita Merello y
  El Noba) aportan 67 de los 175 fragmentos (38 %). El estilo de esos artistas
  pesa en los resultados.
- **Origen de 27 fragmentos verificado a mano.** Una parte de los artistas no
  pasó por la verificación automática de origen con Wikidata y MusicBrainz: su
  procedencia porteña la chequeó el grupo, y esos fragmentos quedan marcados
  con `origin_source: verificacion_manual_grupo`.
- **`viste` no tiene respaldo de diccionario.** No figura en el Wikcionario ni
  en diccionarioargentino.com, así que su acepción la redactó el grupo.
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
