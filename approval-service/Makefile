.PHONY: install lint typecheck test migrate run

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

typecheck:
	mypy src/

test:
	pytest -v

migrate:
	alembic upgrade head

run:
	uvicorn approval_service.main:create_app --factory --reload --host 0.0.0.0 --port 8000
