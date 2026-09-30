import { paragraphes } from './texte';

export const formations = [
  { slug: 'no-code', titre: 'Formation no-code : créer une application sans coder', description: "Apprenez à créer applications et automatisations sans code, avec un projet réel accompagné de A à Z.", texte: paragraphes('no-code') },
  { slug: 'ia', titre: 'Formation IA générative pour les entreprises', description: "Intégrer l'IA générative dans les processus de l'entreprise : cas d'usage, outils, conformité.", texte: paragraphes('IA générative') },
  { slug: 'ia-generative', titre: 'Formation prompt engineering et agents IA', description: "Concevoir des prompts fiables et des agents IA qui automatisent des tâches métiers complètes.", texte: paragraphes('agents IA') },
];
