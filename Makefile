.PHONY: install test update backfill reextract rebuild reports site serve e2e geo

install:      ## Python dependencies
	pip install -r requirements.txt

test:         ## unit tests (real SEC filings as fixtures)
	pytest -q

update:       ## incremental run (last 10 days); needs SEC_USER_AGENT
	python -m pipeline.run

backfill:     ## rebuild 24 months of history
	python -m pipeline.run --backfill 730 --rebuild-briefings

reextract:    ## re-run extraction rules on archived filing text (offline)
	python -m pipeline.run --reextract

rebuild:      ## re-derive datasets/briefings from stored evidence (offline)
	python -m pipeline.run --rebuild

reports:      ## weekly/quarterly PDFs + Excel into _site/reports
	python -m pipeline.reporting.build --out _site/reports

site:         ## assemble the GitHub Pages bundle in _site/
	./scripts/build_site.sh

serve:        ## app at http://localhost:8000
	python scripts/serve.py

e2e:          ## browser smoke test against a running server (BASE_URL)
	cd tests/e2e && npm install --no-audit --no-fund && node smoke.mjs

geo:          ## rebuild county/region reference data (rarely needed)
	cd scripts/geo && npm install --no-audit --no-fund && node build_geo.mjs
