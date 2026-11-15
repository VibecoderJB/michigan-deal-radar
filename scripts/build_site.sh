#!/usr/bin/env bash
# Assemble the static site for GitHub Pages: app shell + pipeline data -> _site/
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p _site
cp -R app/. _site/
mkdir -p _site/data
# Publish datasets only: the evidence text archive and v1 backups stay in the repo, not on the site.
DATA_DIR="${MDR_DATA_DIR:-data}"
rsync -a --exclude 'evidence_text/' --exclude 'backup/' --exclude 'evidence.json' "$DATA_DIR"/ _site/data/ 2>/dev/null || {
  cp -R "$DATA_DIR"/. _site/data/ && rm -rf _site/data/evidence_text _site/data/backup _site/data/evidence.json; }
# Bust the service-worker cache on every deploy so clients pick up new app code.
stamp="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
sed -i.bak "s/const VERSION = \"mdr-v[^\"]*\"/const VERSION = \"mdr-${stamp}\"/" _site/sw.js && rm -f _site/sw.js.bak
touch _site/.nojekyll
echo "Built _site ($(find _site -type f | wc -l) files, version ${stamp})"
