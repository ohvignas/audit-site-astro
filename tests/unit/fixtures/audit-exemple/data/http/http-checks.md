# Contrôles HTTP — exemple.test

| Contrôle | Valeur | Verdict |
|---|---|---|
| Compression HTML | aucune (HTML décompressé : 42 Ko) | ❌ activer brotli/gzip (proxy, CDN ou middleware) |
| Favicon déclaré | /favicon.svg | ✅ |
| Server / X-Powered-By | nginx/1.24.0 / — | ⚠️ version exposée |
