.PHONY: install test lint format coverage

install:
	python -m pip install -r requirements-dev.txt

test:
	python -m pytest -q

coverage:
	pytest --cov=src --cov-report=term-missing

lint:
	flake8 src test

format:
	black src test
	isort src test
