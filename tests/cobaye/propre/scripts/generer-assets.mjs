import sharp from 'sharp';
import { mkdirSync } from 'node:fs';
mkdirSync('src/assets', { recursive: true });
const bruit = (w, h) => sharp({ create: { width: w, height: h, channels: 3, noise: { type: 'gaussian', mean: 128, sigma: 60 } } });
await bruit(2400, 1600).jpeg({ quality: 85 }).toFile('src/assets/hero.jpg');
await bruit(512, 128).png().toFile('src/assets/logo.png');
await bruit(1200, 800).jpeg({ quality: 85 }).toFile('src/assets/schema.jpg');
console.log('assets du cobaye propre générés');
