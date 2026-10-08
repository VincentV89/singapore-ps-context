.PHONY: install test build dev-api dev-web

install:
	python -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt boto3
	cd frontend && npm ci --cache ../.npm-cache

test:
	.venv/bin/python -m unittest discover -s backend/tests -v
	.venv/bin/python -m unittest discover -s infra/tests -v
	cd frontend && npm run build

build:
	cd frontend && npm run build

dev-api:
	.venv/bin/python backend/local_server.py

dev-web:
	cd frontend && npm run dev
