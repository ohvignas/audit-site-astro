import { paragraphes } from './texte';

export const formations = [
  // S14 : pas de description — S22 : contenu faible
  { slug: 'no-code', titre: 'Formation no-code', description: '', texte: ['Apprenez le no-code avec nous.'] },
  // S15 : description dupliquée — S34 : titres quasi identiques
  { slug: 'ia', titre: 'Formation IA générative pour les entreprises', description: 'Une formation complète.', texte: paragraphes('IA générative') },
  { slug: 'ia-generative', titre: 'Formation IA générative pour entreprises', description: 'Une formation complète.', texte: paragraphes('IA pour entreprises') },
];
