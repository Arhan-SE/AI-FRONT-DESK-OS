# CLAUDE.md — AI Business Operating System

## 1. Project Overview

Build a production-quality competition prototype called:

**AI Business Operating System for Home Service Businesses**

The system acts as an AI-powered operational layer for HVAC, plumbing, electrical, cleaning, and similar home-service businesses.

It manages the customer lifecycle:

**Lead → Qualification → Appointment → Service → Payment → Review → Retention → Reactivation**

The system is not merely a chatbot. It combines AI reasoning, voice interaction, customer memory, business logic, scheduling, automation, analytics, and human escalation.

The project must look and behave like a serious enterprise product while remaining practical to build and demonstrate.

---

# 2. Primary Objectives

1. Build a reliable end-to-end AI business system.
2. Demonstrate real AI decision-making rather than simple LLM text generation.
3. Keep the architecture modular and explainable.
4. Avoid unnecessary third-party SaaS dependencies.
5. Prefer open-source/self-hosted/free components where practical.
6. Never compromise reliability merely to add another feature.
7. Prioritize the competition demo experience.
8. Keep the UI minimalist, monochrome, premium, and highly usable.
9. Make all important AI decisions observable and auditable.
10. Build reusable infrastructure instead of duplicating logic.

---

# 3. Technology Stack

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- Lucide React
- Recharts
- LiveKit client SDK for in-browser voice calls
- Supabase JS client, used for reads only

## Repository layout

Two top-level applications, split by language:

```text
frontend/   React + TypeScript
backend/    Python — one package, three entry points (api, agent, automation)
db/         migrations and seed data
```

The backend is a single Python package with a single virtual environment. The
API, the voice agent, and the automation worker are separate processes that
import the same shared `domain` layer.

## Backend

- Python
- FastAPI
- Pydantic

## AI / Voice

OpenAI is the only AI provider. One API key for the entire system.

- LiveKit Agents, joined from the browser over WebRTC
- OpenAI Realtime API for the voice conversation
- `gpt-4o-mini` (text) for all server-side reasoning and decisions
- `text-embedding-3-small` (1536 dimensions) for semantic memory
- A deterministic fake provider for tests and demo mode

All of the above sit behind a provider abstraction so the voice model can fall
back to an STT/LLM/TTS pipeline without a rewrite.

### Division of labour

The Realtime model handles conversation. It does not make business decisions.

- **Realtime model:** listening, speaking, turn-taking, calling tools.
- **Server-side `gpt-4o-mini`:** intent classification, entity extraction, lead
  qualification, memory retrieval, campaign eligibility.

This keeps expensive audio tokens doing only what they are uniquely good at, and
keeps every business decision testable, loggable, and auditable.

Capabilities:

- Tool/function calling
- Intent classification
- Entity extraction
- Lead qualification
- Customer-memory retrieval

## Database

- Supabase
- PostgreSQL
- pgvector
- Supabase Auth
- PostgreSQL Row Level Security

## Automation

- Custom Python Automation Engine
- FastAPI-compatible service layer
- PostgreSQL-backed scheduled jobs
- Background worker for executing automation jobs

All automation is implemented in Python.

n8n and other external workflow platforms are NOT part of this architecture.
Do not introduce them. Automation complexity belongs in typed, tested Python.

## Scheduling

- Native scheduling engine built on PostgreSQL
- Availability derived from technician schedules, business hours, and service duration
- Atomic booking enforced by a database exclusion constraint
- Short-lived slot holds for in-conversation booking
- Read-only iCal feed export for technician calendar subscription

No external scheduling service. The `appointments` table is the single source of truth.

## Messaging

- Official Telegram Bot API
- **Long polling** for inbound updates, not webhooks
- Inline keyboards for structured customer replies

Long polling is used because the system runs on localhost and has no public URL.
The backend calls out to Telegram; Telegram never calls in. No tunnel required.

The inbound handler is written so a webhook transport can replace long polling
later without touching the update-handling logic.

Telegram is the only messaging channel.

Do NOT add WhatsApp, SMS, or email channels unless explicitly requested.
Do NOT use unofficial clients, scraping, or userbot automation. Use the official Bot API only.

## Runtime

The system runs entirely on a local machine. There are no containers.

- No Docker, no Docker Compose, no reverse proxy.
- Supabase is hosted, so there is no local database to run.
- LiveKit is hosted; the agent connects outbound to it.

Four local processes:

```text
frontend      vite dev server           http://localhost:5173
api           uvicorn                   http://localhost:8000
agent         LiveKit voice worker      outbound only
automation    scheduler + jobs + Telegram long poll
```

Nothing needs to be reachable from the internet. Every external connection is
outbound, which is what makes the localhost setup work without tunnelling.

Run each process in its own terminal, or use the Makefile targets.

---

# 4. Architecture

The system must maintain a strict separation of responsibility.

```text
Customer
   │
   ▼
Browser (React + WebRTC)
   │   ← token minted by FastAPI
   ▼
LiveKit
   │
   ▼
Voice Agent (OpenAI Realtime)
   │
   ▼
FastAPI
   │
   ├── AI / decision logic
   ├── Customer memory
   ├── Lead qualification
   ├── Emergency detection
   ├── Business rules
   ├── Tool orchestration
   └── Automation services
   │
   ├───────────────┬────────────────────┐
   ▼               ▼                    ▼
Supabase       Scheduling      Python Automation Engine
Database        Engine                  │
   │          (PostgreSQL)              ▼
   │                             Communication Guard
   │                                    │
   │                                    ▼
   │                            Telegram Bot API
   │                                    │
   ▼                                    ▼
Dashboard                            Customer
```

### Responsibility rules

- **LiveKit:** real-time voice communication.
- **LLM:** reasoning, understanding, extraction, generation.
- **FastAPI:** business logic, AI orchestration, validation, tool execution.
- **Supabase:** canonical application data and customer memory.
- **pgvector:** semantic memory and RAG.
- **Python Automation Engine:** scheduled/repetitive workflow execution.
- **Scheduling Engine:** availability calculation and appointment booking.
- **Telegram Bot API:** message delivery.
- **React:** application interface.

Do not move business-critical logic into the frontend.

Supabase PostgreSQL is the only canonical datastore.

### Data access rules

The frontend uses a split data path:

- **Reads:** React queries Supabase directly using the anon key and the signed-in
  user's JWT. This keeps the interface fast and avoids hundreds of pass-through
  endpoints.
- **Writes:** every mutation goes through FastAPI using the service-role key.
  The frontend never writes to the database.

Because the anon key ships inside the JavaScript bundle, Row Level Security is
the primary access control for the read path, not a secondary safeguard.

- RLS policies are written in the same migration as the table they protect.
  Never as a later retrofit pass.
- The authenticated role gets `SELECT` only. No `INSERT`, `UPDATE`, or `DELETE`.
- Policies are scoped by `business_id`, derived from the verified JWT and never
  from a client-supplied value.
- A smoke test covers cross-tenant isolation.

RLS may be relaxed during local development. It must be enabled before the
application is reachable from a public URL.

---

# 5. Current Product Features

## AI Customer Interaction

- AI Voice Agent, started from the browser
- AI Customer Query Handling
- Lead Qualification
- Long-Term Customer Memory

## Appointment & Service Management

- AI Appointment Booking
- Appointment Reminders
- Post-Service Follow-ups

## Revenue & Retention

- Payment Reminders
- Review Collector
- Lead Reactivation
- Seasonal Campaigns

## Future

- Emergency Detection (deferred, see section 8)
- AI Administrative Manager
- Multi-regional language support

Future features must not destabilize the current system.

---

# 6. AI Agent Rules

The voice agent should not directly manipulate the database without controlled tools.

Use explicit tools such as:

```text
identify_customer()
search_customer_memory()
get_customer_history()
create_lead()
score_lead()
detect_emergency()
get_available_slots()
book_appointment()
get_invoice_status()
create_follow_up()
request_review()
create_reactivation_task()
escalate_to_human()
```

Tools must:

- Validate inputs.
- Return structured results.
- Handle errors.
- Log important actions.
- Never silently fail.

The agent should not invent tool results.

If a tool fails, tell the user appropriately and escalate when necessary.

---

# 7. Lead Qualification

Lead qualification is part of the AI agent/business logic.

Do not build it as an unrelated application.

The agent extracts relevant information and the backend calculates the final score.

Example dimensions:

```text
Intent
Urgency
Service match
Customer value
Engagement
```

Return structured data:

```json
{
  "score": 87,
  "classification": "HOT",
  "confidence": 0.91,
  "reasoning": [
    "Strong service intent",
    "High urgency",
    "Service matches business offering"
  ]
}
```

Do not expose hidden chain-of-thought. Store concise, user-safe decision reasons instead.

---

# 8. Emergency Detection — DEFERRED

Full emergency detection is **not being built in this version**.

Deferred: AI risk classification, LOW/MEDIUM/HIGH scoring, configurable
emergency procedures, and emergency capacity reservation. These remain in the
Future list and the architecture must not preclude them.

## What is still built

A minimal deterministic safety tripwire. No scoring, no LLM classification.

```text
Deterministic keyword match
  (gas, smoke, sparking, burning smell, carbon monoxide, flooding)
        ↓
State plainly that this needs emergency services
        ↓
Escalate to a human
        ↓
Record the event
```

The agent must never provide technical instructions for a potentially dangerous
situation, and must never minimize one.

The system must clearly communicate that it is not a replacement for emergency
services.

When the full capability is built later, it extends this tripwire. It does not
replace it.

---

# 9. Customer Memory

Use two memory layers.

## Structured memory

PostgreSQL:

```text
customers
customer_preferences
service_history
appointments
payments
reviews
```

## Semantic memory

pgvector:

```text
conversation summaries
important customer interactions
business documents
relevant historical context
```

Do not continuously send the customer's entire history to the LLM.

Retrieve only relevant context.

Memory retrieval must be scoped to the correct customer/business.

---

# 10. Communication Engine

All automated customer messaging should use one reusable communication pipeline.

Features:

- Appointment reminders
- Post-service follow-ups
- Payment reminders
- Review requests
- Lead reactivation
- Seasonal campaigns

Conceptual API:

```text
send_customer_message(
    customer_id,
    message_type,
    context
)
```

All message types must pass through the Communication Guard.

---

# 11. Communication Guard

Before sending automated communication, verify:

- Customer identity.
- Appropriate channel.
- Consent/opt-in where required.
- Transactional vs marketing classification.
- Frequency limits.
- Do-not-contact status.
- Previous recent messages.
- Duplicate-message prevention.
- Campaign eligibility.

If validation fails:

```text
DO NOT SEND
```

Do not bypass the guard for convenience.

Marketing communication must support opt-out handling.

---

# 12. Python Automation Engine Rules

Automation is implemented directly in Python.

Do not create separate scripts that run independently without a shared job model.

Use a central automation system with:

```text
automation/
├── scheduler.py
├── worker.py
├── jobs/
│   ├── appointment_reminders.py
│   ├── post_service_followups.py
│   ├── payment_reminders.py
│   ├── review_requests.py
│   ├── lead_reactivation.py
│   └── seasonal_campaigns.py
├── communication/
│   ├── guard.py
│   ├── telegram.py
│   ├── templates.py
│   ├── rate_limit.py
│   └── preferences.py
└── services/
    ├── customer_service.py
    ├── appointment_service.py
    ├── payment_service.py
    └── campaign_service.py
```

Use a PostgreSQL-backed job table for scheduled work.

Example:

```text
automation_jobs

id
job_type
scheduled_for
status
attempts
payload
last_error
created_at
completed_at
```

Worker lifecycle:

```text
Scheduler
   ↓
Find pending jobs
   ↓
Claim job
   ↓
Execute business logic
   ↓
Communication Guard
   ↓
External API
   ↓
Record result
```

Critical jobs must be idempotent.

A retry must not result in duplicate:

- Appointments
- Messages
- Payment reminders
- Campaign actions

Automation must use the same business services and Communication Guard as agent-triggered actions.

## 12.1 Automation Features

The automation engine should support:

### Appointment Reminders

```text
Appointment approaching
    ↓
Load appointment/customer
    ↓
Check communication preferences
    ↓
Communication Guard
    ↓
Send approved reminder
    ↓
Record result
```

### Post-Service Follow-ups

```text
Job completed
    ↓
Schedule follow-up job
    ↓
Retrieve customer/service context
    ↓
Communication Guard
    ↓
Send follow-up
```

### Payment Reminders

```text
Invoice overdue
    ↓
Check payment state
    ↓
Check reminder history
    ↓
Communication Guard
    ↓
Send reminder
```

### Lead Reactivation

```text
Find inactive customers
    ↓
Calculate reactivation eligibility/score
    ↓
Select campaign
    ↓
Communication Guard
    ↓
Send approved message
    ↓
Track response
```

### Review Collection

```text
Job completed
    ↓
Wait configured period
    ↓
Check review eligibility
    ↓
Communication Guard
    ↓
Request review
```

### Seasonal Campaigns

```text
Scheduled seasonal event
    ↓
Find eligible customers
    ↓
Apply business rules
    ↓
Communication Guard
    ↓
Create/send campaign messages
```

# 13. Database Rules

Supabase PostgreSQL is the source of truth.

Expected major entities:

```text
businesses
users
customers
customer_preferences
customer_memory
conversations
messages
leads
lead_scores
appointments
services
technicians
technician_schedules
technician_time_off
business_hours
business_holidays
slot_holds
invoices
payments
campaigns
campaign_recipients
message_templates
reviews
tasks
automation_jobs
ai_decisions
notifications
audit_logs
```

Scheduling integrity is enforced in the database, not only in application code:

- An exclusion constraint on `appointments` makes overlapping bookings for the
  same technician impossible.
- `slot_holds` reserve offered slots for a short TTL so concurrent conversations
  cannot be offered the same time.
- Idempotency keys ensure a retried booking returns the existing appointment.

Customer messaging identity is `customers.telegram_chat_id`, populated only
through an explicit opt-in link. A customer without a chat ID cannot be messaged.

Every table must have clear ownership/relationship rules.

Use migrations.

Do not manually modify production schema without a migration.

Use Row Level Security for multi-business data isolation.

Never hard-code database credentials.

Never commit `.env` files or secrets.

---

# 14. API Rules

FastAPI endpoints should be:

- Small
- Typed
- Validated
- Authenticated where required
- Consistent in response format
- Properly error-handled

Use Pydantic models for request/response validation.

Do not return arbitrary database objects directly to the frontend.

Use service layers for business logic.

---

# 15. Error Handling

Every external operation must account for failure.

Examples:

- LLM unavailable
- Voice provider unavailable
- Telegram Bot API failure or rate limit
- Database timeout
- Automation job failure
- Slot no longer available at booking time
- Invalid customer data

Never silently fail.

UI must display an appropriate error state.

Backend must log enough information to debug the issue without leaking secrets.

---

# 16. UI / UX

The application must be:

**Minimalist + Premium + Monochrome + Enterprise**

Primary colors:

- Black
- White
- Neutral grays

Avoid:

- Gradients
- Excessive rounded cards
- Neon colors
- Decorative animations
- Unnecessary illustrations
- Excessive glassmorphism
- Cluttered dashboards

Use color only when it communicates important state, especially emergency/status information.

Use:

- Tailwind CSS
- shadcn/ui
- Consistent spacing
- Strong typography
- Clear hierarchy
- Tables for operational data
- Whitespace

---

# 17. Main Navigation

```text
Overview
AI Activity
Leads
Customers
Appointments
Conversations
Campaigns
Reviews
Payments
Insights
Settings
```

The AI Administrative Manager may become a dedicated section later.

---

# 18. UI Reliability

Every asynchronous UI operation needs:

- Loading state
- Success state
- Error state
- Retry where appropriate
- Empty state

Never:

- Leave buttons spinning forever.
- Silently fail.
- Lose user input after an API failure.
- Allow accidental duplicate submissions.
- Display raw stack traces.

Destructive operations require confirmation.

---

# 19. AI Activity

The AI Activity page is a primary competition feature.

Show events such as:

```text
Incoming customer conversation
Customer identified
Intent detected
Memory retrieved
Emergency probability calculated
Lead score calculated
Availability checked
Appointment booked
Confirmation sent
```

Each event should show:

- Timestamp
- Event type
- Status
- Relevant context
- Result
- Confidence when applicable

Do not expose private chain-of-thought.

---

# 20. Competition Demo Mode

Create a deterministic demo environment.

It should support scenarios:

1. Normal customer inquiry.
2. High-value lead.
3. Emergency request.
4. Appointment booking.
5. Completed job → follow-up.
6. Overdue payment → reminder.
7. Dormant customer → reactivation.

Demo mode should use seeded data and controlled responses where necessary so the presentation does not depend entirely on unpredictable external services.

The real integrations should still exist, but the demo must have a reliable fallback.

---

# 21. Development Rules

Before adding a dependency:

1. Check whether an existing dependency already solves the problem.
2. Prefer standard library or existing project utilities.
3. Prefer open-source/self-hosted options.
4. Avoid adding SaaS merely for convenience.
5. Check compatibility with the existing architecture.
6. Keep dependencies minimal.

Do not rewrite working systems unnecessarily.

Do not introduce multiple libraries for the same responsibility.

---

# 22. Code Quality

Write code that is:

- Readable
- Typed
- Modular
- Testable
- Explicit
- Documented where necessary

Avoid:

- Giant components
- Giant functions
- Duplicate logic
- Magic constants
- Hard-coded customer/business data
- Hard-coded secrets
- Unnecessary abstractions

Prefer small focused modules.

---

# 23. Testing

Before considering a feature complete:

### Backend

- Unit test important business logic.
- Test validation.
- Test failure states.
- Test authorization.

### Frontend

- Test critical interactions.
- Test loading/error/empty states.
- Verify responsive behavior.

### AI

Test representative scenarios:

- Normal customer
- High-value lead
- Emergency
- Returning customer
- Unknown customer
- Ambiguous request
- Tool failure

### Integrations

Test:

- Database
- Row Level Security / cross-tenant isolation
- Scheduling and slot holds
- Telegram messaging
- Voice

---

# 24. Security

Never commit:

- API keys
- Access tokens
- Database passwords
- Supabase service-role keys
- Telegram bot tokens
- LLM keys
- LiveKit secrets

Use environment variables.

Use separate development/demo/production credentials.

Validate every inbound Telegram update before acting on it.

Never trust a chat ID, customer identity, or business ID supplied by a client.

Enforce authorization server-side.

---

# 25. Git Rules

Use meaningful commits:

```text
feat: add lead qualification
feat: add appointment booking
feat: add customer memory
fix: prevent duplicate reminders
refactor: extract communication service
docs: update architecture
```

Do not commit generated files, secrets, local databases, or temporary debug files.

---

# 26. Claude Code Workflow

Before implementing a major feature:

1. Inspect the existing repository.
2. Identify affected modules.
3. Check existing patterns.
4. Propose the smallest clean implementation.
5. Implement.
6. Run tests/type checks/linting.
7. Verify the UI.
8. Fix regressions.
9. Update documentation.

Do not blindly overwrite existing files.

Do not create duplicate components/services when an existing one can be extended.

---

# 27. Definition of Done

A feature is not complete when the happy path works.

It is complete when:

- Happy path works.
- Invalid input is handled.
- External failure is handled.
- Loading state exists.
- Empty state exists.
- Error state exists.
- Data is persisted correctly.
- Authorization is respected.
- Duplicate actions are prevented.
- Logs/audit records exist where appropriate.
- UI matches the design system.
- No obvious console errors remain.
- Tests pass.

---

# 28. Product Philosophy

The project should demonstrate:

> **AI that understands, decides, acts, remembers, and knows when to involve a human.**

Avoid presenting it as:

> "A chatbot with lots of integrations."

Every feature should reinforce the central architecture.

The system should feel like:

**One AI Business Operating System.**

Not a collection of unrelated tools.

---

# 29. Priority Order

When deciding what to build next, use this order:

1. Core architecture
2. Scheduling engine
3. Voice agent (browser)
4. Customer memory
5. Lead qualification
6. Appointment booking
7. Communication engine
8. Follow-ups
9. Payment reminders
10. Lead reactivation
11. Review collection
12. Seasonal campaigns
13. AI Activity dashboard
14. Analytics
15. Emergency detection (deferred)
16. AI Administrative Manager
17. Multilingual support

Do not build future features at the expense of reliability of the core system.

---

# 30. Final Principle

**Reliability beats feature count.**

A smaller system that works flawlessly during the competition is more valuable than a huge system with broken integrations.

Build the smallest technically credible version first.

Then expand.
