/**
 * Builds the Google Form for the speaker from Spain (stage 05).
 *
 * 1. Import data/annotation/hablante_es/formulario.csv into a new Google Sheet
 *    (File > Import > Upload, "Replace current sheet").
 * 2. In that sheet: Extensions > Apps Script, paste this file and run
 *    buildSpeakerForm. Google asks once for permission to create the form.
 * 3. The log (View > Logs) prints the link to send and the link to edit.
 *
 * The form shows the questions in the order of the file and the options in
 * their fixed order (A-D); neither is shuffled. Answers are graded with
 * python -m pipeline.stage05_speaker --grade.
 */

const QUESTIONS_PER_PAGE = 10;

function buildSpeakerForm() {
  const rows = SpreadsheetApp.getActiveSheet().getDataRange().getValues();
  const header = rows[0].map(String);
  const col = (name) => {
    const i = header.indexOf(name);
    if (i < 0) throw new Error('Missing column: ' + name);
    return i;
  };
  const items = rows.slice(1).filter((r) => String(r[col('n')]).trim() !== '');

  const form = FormApp.create('Vocabulario en letras de canciones');
  form.setDescription(
    'Vas a leer ' + items.length + ' fragmentos de canciones. En cada uno hay una ' +
    'palabra señalada: elige qué significa en ese fragmento. Responde con lo ' +
    'primero que entiendas, sin buscar en internet. Lleva unos 15 minutos.'
  );
  form.setProgressBar(true);
  form.setShuffleQuestions(false);
  form.setCollectEmail(false);

  items.forEach((r, i) => {
    if (i > 0 && i % QUESTIONS_PER_PAGE === 0) {
      form.addPageBreakItem().setTitle('Seguimos');
    }
    const n = r[col('n')];
    const word = r[col('palabra')];
    form.addMultipleChoiceItem()
      .setTitle(n + '. ¿Qué significa «' + word + '» en este fragmento?')
      .setHelpText(String(r[col('fragmento')]))
      .setChoiceValues(['A', 'B', 'C', 'D'].map((l) => l + ') ' + r[col(l)]))
      .setRequired(true);
  });

  Logger.log('Link to send: ' + form.getPublishedUrl());
  Logger.log('Link to edit: ' + form.getEditUrl());
}
