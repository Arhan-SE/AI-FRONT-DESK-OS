# Genesis OS — runbook

AI operating system for home-service businesses. Five processes, all on this
machine. Nothing listens on the public internet.

---

## Before you start

Check these once. If they were fine yesterday they are fine today.

```bash
node -v        # 26.x
python3 -V     # 3.12+
uv --version
livekit-server --version
```

The only file you need is `.env` at the repository root. It is gitignored and
already filled in.

---

## Starting up — five terminals

Run each in its own terminal, **in this order**. Order matters only for the
agent, which needs LiveKit already listening.

### Terminal 1 — LiveKit

```bash
make livekit
```

Wait for: `starting LiveKit server ... "portHttp": 7880`

### Terminal 2 — API

```bash
make api
```

Wait for: `ready — postgres 17.6, 5 customers, N appointments`

A warning about `TELEGRAM_BOT_TOKEN not set` is expected until a token is
configured. It is not an error.

### Terminal 3 — Voice agent

```bash
make agent
```

Wait for: `registered worker`

If this says `ws_url is required` the LiveKit server is not up yet — start
terminal 1 first.

### Terminal 4 — Automation worker

```bash
make automation
```

Wait for: `worker started — postgres 17.6`

This drains the job queue every 10 seconds and polls Telegram for replies.

### Terminal 5 — Dashboard

```bash
make web
```

Wait for: `Local: http://localhost:5173/`

---

## Verify before presenting

```bash
make dev-check
```

Checks every process, the database, both credentials, and — the one that is
easy to miss — whether LiveKit is still advertising an IP address this machine
actually has. It exits non-zero if anything is wrong.


Open **http://localhost:5173**.

The bottom of the sidebar is the single check that matters:

| Indicator | Meaning |
|---|---|
| ● All systems running | API reachable, everything up |
| ● API unreachable | Terminal 2 died — restart it |
| ● Telegram not configured | Expected until a bot token is set |

Then confirm the API directly:

```bash
curl -s localhost:8000/health | python3 -m json.tool
```

---

## Stopping

`Ctrl-C` in each terminal, or from anywhere:

```bash
pkill -f livekit-server
pkill -f "uvicorn genesis.api"
pkill -f genesis.agent.worker
pkill -f genesis.automation.worker
pkill -f vite
```

---

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Sidebar says API unreachable | uvicorn died | Restart terminal 2 |
| Start call spins, never connects | LiveKit down | Restart terminal 1, then terminal 3 |
| Call connects then drops after a few seconds | Machine's IP changed since LiveKit started — it is advertising the old one | Restart terminal 1. `make dev-check` detects this |
| Agent joins but never speaks | OpenAI key or network | Check terminal 3 output |
| Microphone denied | Browser permission | Allow in site settings, reload |
| Reminders never send | No Telegram token | Expected — the Guard blocks, correctly |
| Jobs board empty after restart | Nothing is lost; data is in Supabase | Reload the page |

Restarting a process is always safe. The database is the source of truth —
there is no in-memory state to lose, and a worker killed mid-job leaves the job
claimable again.

---

## Demo path

1. **Live Call** → Start call → *"Hi, this is Kareem, I need an AC service in Indiranagar"*
2. Watch the right panel while still speaking — identification, lead score, slots, booking
3. **Jobs** → the new booking is there, marked as booked by voice
4. Press **Confirm**, then **Complete**, then **Send invoice**
5. Press **Run due automations** — follow-up, review request and payment reminder all execute
6. **Conversations** → the transcript with the decisions taken beside it
7. **Overview** → counters and cost tiles have moved

---

## Configuration

Everything tunable lives in `backend/src/genesis/settings.py` and is visible on
the **Settings** page: slot hold TTL, follow-up delays, payment terms, quiet
hours, marketing caps, and the model rate card.

Cost figures shown in the product are calculated from those rates. They are not
a bill from the provider — verify against current pricing before quoting a
number.
