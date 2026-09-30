import { useState } from 'react';
export default function Chat() {
  const [ouvert, setOuvert] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOuvert(!ouvert)} aria-label="Ouvrir le chat" className="chat-bouton">💬</button>
      {ouvert && <p>Un conseiller vous répond en moins de 24 h.</p>}
    </div>
  );
}
