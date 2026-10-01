import sharp from 'sharp';
import { mkdirSync } from 'node:fs';
mkdirSync('src/assets', { recursive: true });
// Dégradés (et non du bruit) : un vrai site optimisé sert des images légères ; le bruit du cassé reste, lui, incompressible.
const degrade = (w, h) => sharp(Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><defs>`
  + `<linearGradient id="g"><stop offset="0" stop-color="#1e3a8a"/><stop offset="1" stop-color="#93c5fd"/></linearGradient></defs>`
  + `<rect width="100%" height="100%" fill="url(#g)"/></svg>`));
await degrade(2400, 1600).jpeg({ quality: 85 }).toFile('src/assets/hero.jpg');
await degrade(512, 128).png().toFile('src/assets/logo.png');
await degrade(1200, 630).png().toFile('public/og.png');
await degrade(1200, 800).jpeg({ quality: 85 }).toFile('src/assets/schema.jpg');
console.log('assets du cobaye propre générés');
