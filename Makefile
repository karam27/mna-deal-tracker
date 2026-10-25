.PHONY: install test demo run clean

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	python -m pytest

demo:            ## offline run on the fictional fixtures (no network needed)
	bash scripts/run_pipeline.sh --offline

run:             ## live run against SEC EDGAR and Wikipedia
	bash scripts/run_pipeline.sh

clean:
	rm -rf data/raw data/mna.db data/logs .pytest_cache
