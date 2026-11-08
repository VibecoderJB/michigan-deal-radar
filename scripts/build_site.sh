#!/usr/bin/env bash
# Assemble the static site for GitHub Pages: app shell + pipeline data -> _site/
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p _site
cp -R app/. _site/
mkdir -p _site/data
cp -R data/. _site/data/
# Bust the service-worker cache on every deploy so clients pick up new app code.
stamp="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
sed -i.bak "s/const VERSION = \"mdr-v[^\"]*\"/const VERSION = \"mdr-${stamp}\"/" _site/sw.js && rm -f _site/sw.js.bak
touch _site/.nojekyll
echo "Built _site ($(find _site -type f | wc -l) files, version ${stamp})"
