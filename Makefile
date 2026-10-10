.PHONY: setup test demo demo-replay lint

setup:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

demo:
	python -m revenue_system.cli demo --mode live

demo-replay:
	python -m revenue_system.cli demo --mode replay

lint:
	ruff check .

