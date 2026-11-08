.PHONY: install test update backfill briefings serve site

install:
	pip install -r requirements.txt

test:
	pytest -q

update:            ## incremental run (last 10 days)
	python -m pipeline.run

backfill:          ## rebuild 12 months of history
	python -m pipeline.run --backfill 365

briefings:         ## regenerate all weekly briefings from data/deals.json
	python -m pipeline.run --briefings-only --rebuild-briefings

serve:             ## local app at http://localhost:8000
	python scripts/serve.py

site:              ## assemble the GitHub Pages bundle in _site/
	./scripts/build_site.sh
