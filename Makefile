.PHONY: install test lint format coverage

install:
	python -m pip install -r requirements.txt
	python -m pip install pytest pytest-asyncio pytest-cov httpx black isort flake8

test:
	python -m pytest -q

coverage:
	pytest --cov=src --cov-report=term-missing

lint:
	flake8 src test

format:
	black src test
	isort src test
