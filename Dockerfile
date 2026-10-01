# Audit Site Astro — collecte automatisée (crawl SEO, GEO, HTTP, sécurité, Lighthouse, code Astro/Convex)
FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium python3 curl openssl ca-certificates git bash fonts-liberation \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g lighthouse@12 \
 && npm cache clean --force

ENV CHROME_PATH=/usr/bin/chromium \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PUPPETEER_SKIP_DOWNLOAD=true

WORKDIR /app
COPY plugins/audit-site-astro/skills/audit-complet/scripts/ /app/scripts/
# Fiches de correction : corrections.py les cherche dans ../references/fiches (donc /app/references/fiches)
COPY plugins/audit-site-astro/skills/audit-complet/references/fiches/ /app/references/fiches/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/scripts/*.sh /app/scripts/*.py /app/entrypoint.sh

VOLUME ["/audits"]
ENTRYPOINT ["/app/entrypoint.sh"]
