.PHONY: install test lint format coverage

install:
	python -m pip install -r requirements.txt
	python -m pip install pytest pytest-asyncio pytest-cov black isort flake8

test:
	python -m pytest -q

coverage:
	pytest --cov=./ --cov-report=term-missing

lint:
	flake8 app tests

format:
	black app tests
	isort app tests