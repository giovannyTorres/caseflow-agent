.PHONY: demo check test web-check
demo:
	docker compose up --build -d
check:
	uv run ruff check services tests scripts
	uv run python -m compileall -q services scripts
test:
	uv run pytest -q
web-check:
	cd apps/web && npm run lint && npm run typecheck && npm test && npm run build
