.PHONY: install lint type test audit build check demo

install:
	uv sync --extra dev

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy src/reaper

test:
	uv run pytest --cov=reaper --cov-report=term-missing --cov-fail-under=80

audit:
	uv run pip-audit

build:
	uv build

check: lint type test build audit

demo:
	rm -rf .demo-reaper
	mkdir -p .demo-reaper
	cp reaper.yaml.example .demo-reaper/reaper.yaml
	REAPER_CONFIG=.demo-reaper/reaper.yaml uv run reaper import examples/statements/demo.csv
	REAPER_CONFIG=.demo-reaper/reaper.yaml uv run reaper run --inputs examples/offers.yaml
	REAPER_CONFIG=.demo-reaper/reaper.yaml uv run reaper report --freed-today 31

