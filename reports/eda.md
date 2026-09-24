# Análisis exploratorio de los 90

Números del 24/09/2026, generados con `python -m analysis.eda` y
`python -m analysis.figure_curated` (el detalle está en `eda_numeros.json`). La
capa de cada término es la que propone el filtro; la del grupo sale de la
planilla. Cómo se armaron los 90: `pipeline.md`.

## Por capa

| Capa | Términos | Zipf mediano | En wordfreq | Largo mediano | Subwords del término | Subwords en la letra | Con fragmento B |
|---|---|---|---|---|---|---|---|
| Falsos amigos | 40 | 4,29 | 40 | 5 | 1,18 / 1,32 / 1,35 | 1,27 / 1,52 / 1,48 | 39 |
| Sin homónimo | 20 | 3,29 | 18 | 5,5 | 1,70 / 2,00 / 1,80 | 1,70 / 1,95 / 1,80 | 14 |
| Polisémicos | 15 | 4,29 | 15 | 6 | 1,13 / 1,13 / 1,13 | 1,27 / 1,47 / 1,40 | 15 |
| Controles | 15 | 4,40 | 15 | 5 | 1,13 / 1,13 / 1,13 | 1,07 / 1,13 / 1,13 | 15 |

Subwords promedio en RoBERTuito / BETO / RoBERTa-BNE:
- **del término:** su forma de diccionario (*quemar*);
- **en la letra:** la forma que aparece en el fragmento A (*quemando*), que es
  la que tokeniza el modelo. Es la que va en la Tabla 2 del informe.

**Fuentes de los 75 rioplatenses** (un término puede estar en varias):
- 42 en el diccionario colaborativo;
- 24 en Wiktionary;
- 50 en el Wikcionario.

Los controles salen de wordfreq.

## Contextos

- **173 fragmentos** de 65 canciones de 38 artistas. Hay dos por término,
  salvo 7 términos que tienen uno solo. En 2 términos, A y B son de la misma
  canción.
- **Largo:** mediana de 20 palabras, entre 8 y 25.
- **Flexiones:** en 68 fragmentos (39 %) el término aparece flexionado, como
  *quemando* por *quemar*.
- **Otra palabra:** en 5 términos, uno de los dos fragmentos trae otra palabra
  con la misma forma (*cocina* por *cocinar*). Quedan marcados con
  `forma_de_otra_palabra` y el grupo elige el otro.
- **Figura 1** (`figura_curado.png`): términos de cada capa según la década
  del fragmento A, con el total de cada capa entre paréntesis.
  - 80 de los 90 fragmentos A tienen año según Genius, entre 1910 y 2020.
  - Todas las capas tienen fragmentos de varias épocas.

## Lecturas

1. **Controles.** Quedaron a la par de los falsos amigos: Zipf 4,40 contra
   4,29. Una diferencia de acierto entre esas capas no se explica por
   frecuencia.
2. **Rareza de los sin homónimo.**
   - Son unas diez veces menos frecuentes (Zipf 3,29) y 2 de 20 no están en
     wordfreq.
   - Si un modelo falla más en esa capa, puede ser por rareza: la comparación
     tiene que controlar la frecuencia.
3. **Épocas.** Todas las capas tienen fragmentos de varias décadas, así que
   la tendencia de canciones recientes contra tangos se puede medir, aunque
   con pocos ítems por década.
4. **Subwords.**
   - En el término aislado casi repiten la frecuencia: correlación de −0,86
     con el Zipf. No agregan información aparte.
   - En la forma de la letra, la brecha entre falsos amigos y controles se
     agranda: en BETO pasa de 1,32 contra 1,13 a 1,52 contra 1,13. Salen de
     las flexiones (*pelaron*, *joden*) y de las mayúsculas de comienzo de
     verso (7 de los 40 fragmentos A de falsos amigos), que BETO y RoBERTa-BNE
     parten distinto. RoBERTuito pasa todo a minúsculas.
   - La comparación principal tiene que controlarlo, y la sonda tiene que
     promediar los subwords del término.

## Limitaciones

- **Capa propuesta.** Los números por capa usan la capa del filtro. Se
  recalculan con la capa anotada.
- **Acepción del fragmento.** Que en la letra esté el término no asegura que
  use la acepción de referencia: *vacío* puede aparecer como "vacío" y no
  como corte de carne. Lo decide el grupo al elegir A o B.
- **Pocos artistas.** Cuatro artistas (Edmundo Rivero, El Noba, Zaramay y
  Tita Merello) aportan 66 de los 173 fragmentos (38 %), con 3 canciones cada
  uno. El estilo de esos artistas pesa en los resultados.
- **Año tomado de Genius.** Para tangos suele ser el de una reedición, así que
  las décadas de la Figura 1 son aproximadas.
- **Tokenizador de RoBERTa-BNE.** El repositorio oficial se vació en 2025. Los
  subwords se contaron con una copia idéntica del tokenizador.

## Decisiones pendientes sobre la entrada de los modelos

- **Separador de versos.** Hoy es `" / "`, y el codebook dice que se quitan
  los saltos.
- **Mayúsculas de comienzo de verso.** Al unir los versos, la primera palabra
  de cada uno queda con mayúscula en medio del fragmento (*Cargar*), y los
  modelos que distinguen mayúsculas la parten en más subwords.
