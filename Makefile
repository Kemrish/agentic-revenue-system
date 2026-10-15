.PHONY: setup test lint validate ui worker

setup:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

validate:
	python -m revenue_system.cli validate-packs

ui:
	python -m revenue_system.cli ui

worker:
	python -m revenue_system.cli worker

lint:
	ruff check src tests --select E4,E7,E9,F,I

