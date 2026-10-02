import { useState } from 'react';
export default function Chat() {
  const [ouvert, setOuvert] = useState(false);
  // Garde-fou X03 : classes Tailwind mask-image-* dans le bundle, ne doivent pas passer pour une clé « sk-… »
  return (
    <div>
      <button type="button" onClick={() => setOuvert(!ouvert)} aria-label="Ouvrir le chat" className="chat-bouton mask-image-b-from-color mask-image-b-to-color">💬</button>
      {ouvert && <p>Un conseiller vous répond en moins de 24 h.</p>}
    </div>
  );
}
