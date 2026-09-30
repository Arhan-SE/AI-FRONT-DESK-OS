.PHONY: help setup livekit api agent automation web dev-check db-push seed test lint

help:
	@echo "Genesis OS — AI Business Operating System"
	@echo ""
	@echo "  make setup       install backend + frontend dependencies"
	@echo "  make api         run FastAPI on :8000                (terminal 1)"
	@echo "  make agent       run the LiveKit voice agent          (terminal 2)"
	@echo "  make automation  run the scheduler + worker + Telegram poll (terminal 3)"
	@echo "  make web         run the Vite dev server on :5173     (terminal 4)"
	@echo ""
	@echo "  make livekit     run a self-hosted LiveKit server instead of LiveKit Cloud"
	@echo "                   only needed if LIVEKIT_URL in .env is ws://localhost:7880"
	@echo ""
	@echo "  make db-push     apply db/migrations in order"
	@echo "  make seed        generate demo business history"
	@echo "  make test        backend tests"
	@echo "  make dev-check   verify tools and env before a demo"

setup:
	cd backend && uv sync
	cd frontend && npm install

# Terminal 1
api:
	cd backend && uv run uvicorn genesis.api.main:app --reload --port 8000

# Terminal 2 — LiveKit Cloud, not a local server. The agent connects outbound
# to the wss://*.livekit.cloud project configured as LIVEKIT_URL in .env;
# there is nothing else to start for it. `make dev-check` verifies that
# project directly with an authenticated API call.
agent:
	cd backend && uv run python -m genesis.agent.worker dev

# Terminal 3
automation:
	cd backend && uv run python -m genesis.automation.worker

# Terminal 4
web:
	cd frontend && npm run dev

# Optional fallback — a self-hosted LiveKit server for offline development,
# in place of LiveKit Cloud. Only relevant if LIVEKIT_URL in .env is set back
# to ws://localhost:7880; if it is a wss://*.livekit.cloud project, this
# target is not part of the normal startup sequence.
#
# Dev mode uses the well-known devkey/secret pair.
#
# LiveKit detects this machine's IP at startup and advertises it as its ICE
# candidate, while binding its media socket to the same address. Those two must
# agree, and auto-detection is what keeps them agreeing — do not pin --node-ip
# to loopback, because the media socket does not follow it and every call then
# dies at "connecting -> disconnected".
#
# --bind pins the address *family*, not the address value, so it does not
# fight that auto-detection. Without it, a network that hands out a routable
# IPv6 address (common on home Wi-Fi) can make LiveKit auto-select IPv6 for
# media while the browser and `make dev-check` only ever look for IPv4 — a
# silent mismatch, not a crash. Loopback must stay in the list alongside the
# LAN IP: the browser's signalling connection is `ws://localhost:7880`, and
# dropping 127.0.0.1 from the bind set breaks that even though media is fine.
#
# The consequence that remains: if the machine's IP changes (new network,
# DHCP renewal), LiveKit is still advertising the old one. Restart this
# process if so — `make dev-check` detects it.
livekit:
	livekit-server --dev --bind 127.0.0.1 --bind $$(ipconfig getifaddr en0)

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
