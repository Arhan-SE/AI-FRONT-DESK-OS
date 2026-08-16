.PHONY: help setup livekit api agent automation web dev-check db-push seed test lint

help:
	@echo "Genesis OS — AI Business Operating System"
	@echo ""
	@echo "  make setup       install backend + frontend dependencies"
	@echo "  make livekit     run the self-hosted LiveKit server (terminal 1)"
	@echo "  make api         run FastAPI on :8000                (terminal 2)"
	@echo "  make agent       run the LiveKit voice agent          (terminal 3)"
	@echo "  make automation  run the scheduler + worker + Telegram poll (terminal 4)"
	@echo "  make web         run the Vite dev server on :5173     (terminal 5)"
	@echo ""
	@echo "  make db-push     apply db/migrations in order"
	@echo "  make seed        generate demo business history"
	@echo "  make test        backend tests"
	@echo "  make dev-check   verify tools and env before a demo"

setup:
	cd backend && uv sync
	cd frontend && npm install
	@echo "Install the LiveKit server if missing: brew install livekit"

# Terminal 1 — dev mode uses the well-known devkey/secret pair and binds
# localhost only. Media stays on this machine.
livekit:
	livekit-server --dev

# Terminal 2
api:
	cd backend && uv run uvicorn genesis.api.main:app --reload --port 8000

# Terminal 3
agent:
	cd backend && uv run python -m genesis.agent.worker dev

# Terminal 4
automation:
	cd backend && uv run python -m genesis.automation.worker

# Terminal 5
web:
	cd frontend && npm run dev

db-push:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL not set — source your .env first" && exit 1)
	@for f in db/migrations/*.sql; do \
		echo "→ $$f"; \
		psql "$$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f $$f || exit 1; \
	done
	@echo "migrations applied"

seed:
	cd backend && uv run python -m genesis.db.seed

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check src tests
	cd frontend && npm run lint

# Run this before the demo. Catches the failures that are embarrassing to find
# on stage: missing binaries, unset keys, unreachable services.
dev-check:
	@cd backend && uv run python -m genesis.db.healthcheck
