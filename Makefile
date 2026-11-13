makefile
.PHONY: run test lint

run:
	python -m depgraph --help

test:
	pytest -q

lint:
	python -m flake8 --max-line-length=80 src tests
