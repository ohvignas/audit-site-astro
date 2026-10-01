// Génère au build ce qu'on ne veut pas versionner : images lourdes, module JS de 300 Ko, faux secret.
import sharp from 'sharp';
import { mkdirSync, writeFileSync } from 'node:fs';

for (const d of ['public/images', 'src/assets', 'src/lib']) mkdirSync(d, { recursive: true });
const bruit = (w, h) => sharp({ create: { width: w, height: h, channels: 3, noise: { type: 'gaussian', mean: 128, sigma: 60 } } });

await bruit(4000, 2667).jpeg({ quality: 95 }).toFile('public/images/hero-4000.jpg'); // P02 : 4000 px brut dans public/
await bruit(4000, 2667).jpeg({ quality: 92 }).toFile('src/assets/hero.jpg');          // H12 : lourd à transformer par /_image
await bruit(1600, 1600).png().toFile('public/images/storage-logo.png');               // P14 : « storage Convex » brut
await bruit(800, 600).png().toFile('public/images/schema.png');                      // P13 : image Markdown dans public/

// P04 : ~330 Ko de chaînes pseudo-aléatoires (peu compressibles) importées par l'îlot Chat
let graine = 42;
const alea = () => ((graine = (graine * 1103515245 + 12345) % 2147483648) / 2147483648).toString(36).slice(2, 14);
const lignes = Array.from({ length: 6000 }, (_, i) => `  "c${i}": "${alea()}${alea()}${alea()}${alea()}",`);
writeFileSync('src/lib/gros-module.ts', `export const dictionnaire: Record<string, string> = {\n${lignes.join('\n')}\n};\n`);

// X03 : faux secret reconstitué ici pour ne jamais apparaître tel quel dans le dépôt
const faux = ['sk', 'live', 'COBAYE0FAUX0SECRET0NE0PAS0UTILISER'].join('_');
writeFileSync('src/lib/faux-secret.ts', `export const FAUX_SECRET = '${faux}';\n`);
console.log('assets du cobaye générés');
