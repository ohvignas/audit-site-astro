import { useState } from 'react';
import { dictionnaire } from '../lib/gros-module'; // P04 : 300 Ko chargés au démarrage

export default function Chat() {
  const [ouvert, setOuvert] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOuvert(!ouvert)} aria-label="Ouvrir le chat">💬</button>
      {ouvert && <p>{Object.keys(dictionnaire).length} réponses disponibles</p>}
    </div>
  );
}
