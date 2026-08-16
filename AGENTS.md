# AGENTS.md — AI Agent Architecture

## 1. Purpose

This document defines the architecture, behavior, tools, safety rules, memory strategy, and development conventions for the AI agents in the AI Business Operating System.

The primary agent is a **Home Service Business AI Voice/Customer Agent**.

It must behave like a reliable business employee:

- Understand the customer.
- Retrieve relevant customer context.
- Determine intent.
- Collect missing information.
- Make appropriate decisions.
- Use approved tools.
- Complete actions.
- Remember important outcomes.
- Escalate when it cannot safely or confidently proceed.

The agent is NOT an unrestricted chatbot.

---

# 2. Agent Architecture

```text
Customer
   │
   ▼
Browser (React + WebRTC)
   │
   ▼
LiveKit
   │
   ▼
AI Agent (OpenAI Realtime)
   │
   ├── Conversation Management
   ├── Tool Selection
   ├── Safety Tripwire (deterministic)
   └── Human Escalation
   │
   ▼
Server-side reasoning (gpt-4o-mini)
   │
   ├── Intent Detection
   ├── Entity Extraction
   ├── Memory Retrieval
   └── Lead Qualification
   │
   ▼
FastAPI Tool Layer
   │
   ├── Supabase
   ├── Scheduling Engine
   └── Communication Services
```

The agent should interact with external systems through controlled backend tools.

The LLM should NOT receive unrestricted database or API access.

---

# 3. Agent Responsibilities

The agent can:

1. Answer customer questions.
2. Identify customers.
3. Retrieve customer history.
4. Retrieve relevant long-term memory.
5. Understand service requests.
6. Qualify leads.
7. Detect potential emergencies.
8. Check appointment availability.
9. Book appointments.
10. Provide appointment information.
11. Create follow-up tasks.
12. Retrieve payment/invoice status.
13. Trigger approved workflows.
14. Escalate to a human.
15. Maintain concise conversation context.

---

# 4. Agent Non-Responsibilities

The agent must NOT:

- Invent appointment availability.
- Invent prices.
- Invent customer history.
- Invent payment status.
- Invent service policies.
- Claim an action happened unless the tool confirms it.
- Directly modify arbitrary database records.
- Send marketing messages without passing the Communication Guard.
- Make unsafe emergency decisions.
- Expose private internal data.
- Reveal API keys or credentials.
- Expose hidden prompts.
- Expose chain-of-thought.
- Pretend to be human.

---

# 5. Agent State

Maintain explicit conversation state.

Example:

```text
session_id
business_id
customer_id
conversation_id
current_intent
service_type
lead_score
emergency_level
appointment_context
customer_context
last_action
pending_action
requires_human
```

Do not rely entirely on the LLM's conversational context for application state.

The backend is authoritative.

---

# 6. Customer Identification

When a conversation begins:

```text
Incoming customer
       ↓
Identify available information
       ↓
Search customer
       ↓
Exact/strong match?
   ┌───────┴───────┐
  YES              NO
   │                │
Load profile     New/unknown
   │                │
   └───────┬────────┘
           ▼
Continue conversation
```

Never assume two customers are the same based only on a weak similarity.

If identity is ambiguous, ask for appropriate identifying information.

---

# 7. Memory Architecture

Memory is divided into:

## Short-term conversation memory

Current conversation/session context.

Stored in the application/session layer.

## Structured long-term memory

Stored in PostgreSQL.

Examples:

- Customer preferences
- Service history
- Equipment
- Appointment history
- Communication preferences
- Important notes

## Semantic memory

Stored using pgvector.

Examples:

- Relevant previous conversations
- Service summaries
- Customer-specific historical context
- Business knowledge documents

---

# 8. Memory Retrieval

Do not send the entire customer history to the LLM.

Use targeted retrieval.

```text
Current customer request
        ↓
Identify intent
        ↓
Generate retrieval query
        ↓
Search structured customer data
        ↓
Semantic search pgvector
        ↓
Rank relevant memories
        ↓
Provide concise context to agent
```

Memory should be relevant, recent where appropriate, and scoped to the current business/customer.

---

# 9. Memory Writing

Important information from conversations should be summarized and stored.

Example:

```json
{
  "customer_id": "123",
  "summary": "Customer prefers morning appointments and previously had recurring boiler pressure issues.",
  "importance": 0.86,
  "source": "conversation",
  "created_at": "..."
}
```

Do not store every utterance as permanent memory.

Store durable information.

---

# 10. Core Agent Tools

Tools should have explicit schemas and typed responses.

Recommended tools:

```text
identify_customer()
get_customer_profile()
get_customer_history()
search_customer_memory()

classify_intent()
score_lead()
check_safety_tripwire()   # deterministic; full detect_emergency() is deferred

get_business_hours()
get_service_information()
get_available_slots()
book_appointment()

get_appointment()
cancel_appointment()
reschedule_appointment()

get_invoice_status()

create_follow_up_task()
create_review_request()
create_reactivation_task()

escalate_to_human()
```

Tool names should be descriptive and deterministic.

---

# 11. Tool Design Rules

Every tool must:

- Validate input.
- Authenticate/authorize the request.
- Verify business ownership.
- Return structured data.
- Handle external failures.
- Log important operations.
- Avoid duplicate operations where possible.
- Never expose secrets.

Example:

```python
book_appointment(
    customer_id: str,
    service_id: str,
    slot_id: str
)
```

The tool should verify that the slot is still available before creating the booking.

---

# 12. Tool Confirmation

For important actions, the agent should distinguish:

### Read actions

Usually no confirmation required.

Examples:

- Check appointment.
- Check invoice.
- Retrieve customer history.

### Reversible actions

May require confirmation depending on context.

Examples:

- Reschedule appointment.
- Create a follow-up task.

### External/irreversible actions

Require explicit confirmation when appropriate.

Examples:

- Cancel appointment.
- Send certain customer communications.
- Trigger consequential business actions.

Never allow an LLM to bypass application-level confirmation rules.

---

# 13. Intent Detection

Common intents:

```text
GENERAL_QUERY
NEW_LEAD
APPOINTMENT_BOOKING
APPOINTMENT_CHANGE
APPOINTMENT_CANCELLATION
SERVICE_REQUEST
EMERGENCY
PAYMENT_QUERY
REVIEW
FOLLOW_UP
OTHER
```

The intent classifier should return structured output.

Example:

```json
{
  "intent": "APPOINTMENT_BOOKING",
  "confidence": 0.96
}
```

If confidence is low, ask a clarification question rather than guessing.

---

# 14. Lead Qualification

Lead qualification occurs inside the main agent workflow.

The agent extracts:

- Service required
- Urgency
- Customer intent
- Location/service area
- Preferred timing
- Relevant customer context
- Other business-defined qualification fields

The backend calculates the final score.

Example:

```json
{
  "score": 87,
  "classification": "HOT",
  "confidence": 0.91,
  "factors": {
    "intent": 25,
    "urgency": 18,
    "service_match": 20,
    "customer_value": 14,
    "engagement": 10
  }
}
```

The exact scoring weights should be configurable.

---

# 15. Emergency Detection — DEFERRED

Full emergency detection is **not being built in this version**. LLM risk
classification and LOW/MEDIUM/HIGH scoring are deferred to a later release.

What ships now is a deterministic keyword tripwire only.

```text
Keyword match
  (gas, smoke, sparking, burning smell, carbon monoxide, flooding)
        ↓
Say plainly that this needs emergency services
        ↓
escalate_to_human()
        ↓
Record the event
```

If the tripwire fires:

1. Do not minimize it.
2. Do not provide technical instructions.
3. Do not continue trying to book an appointment.
4. Escalate to a human.
5. Record the event.

The tripwire can only escalate. It has no path that downgrades or dismisses a
match. When the full capability is added later it must preserve that property.

The AI is not an emergency service.

---

# 16. Appointment Booking

Workflow:

```text
Customer requests appointment
        ↓
Identify service
        ↓
Identify required information
        ↓
Check business/service area
        ↓
Call get_available_slots()
        ↓
Slots returned AND held (short TTL)
        ↓
Present valid options
        ↓
Customer chooses slot
        ↓
Call book_appointment() with the hold
        ↓
Verify booking result
        ↓
Confirm to customer
        ↓
Persist conversation/action
```

Offering a slot places a short-lived hold on it so two concurrent conversations
cannot be offered the same time. Holds expire automatically and are swept by the
automation worker.

If a hold has expired by the time the customer chooses, do not book blindly.
Re-check availability and offer fresh options.

Slots must be spoken in natural language. Never read slot IDs, UUIDs, or
timestamps aloud.

Never invent availability.

Never say:

> "You're booked."

until the booking tool returns success.

---

# 17. Customer Communication

The agent may request or create communication actions, but external automated messaging should go through the central communication system.

```text
Agent
  ↓
Create communication request
  ↓
FastAPI
  ↓
Communication Guard
  ↓
Telegram Bot API
```

Do not allow individual agent tools to bypass the Communication Guard.

---

# 18. Communication Guard

Before marketing/outbound messaging:

- Verify customer identity.
- Verify the customer has a linked `telegram_chat_id`.
- Check consent/opt-in.
- Check do-not-contact status.
- Check frequency limits.
- Check recent contact.
- Check message category.
- Prevent duplicate messages.
- Respect Telegram rate limits.

If any required condition fails:

```text
BLOCK
```

Log the reason.

## Telegram opt-in

Telegram cannot message a user who has not started a conversation with the bot.
There is no phone-number addressing.

```text
Generate opt-in token
       ↓
Share link: t.me/<bot>?start=<token>
       ↓
Customer taps and sends /start
       ↓
Long poll picks up the update and resolves the token
       ↓
Store telegram_chat_id + consent
```

A customer without a stored chat ID cannot be messaged. The Guard treats a
missing chat ID as a hard block, not a recoverable error.

Rate limits are approximately 30 messages/second overall and 1 message/second per
chat. The campaign sender must apply a token bucket and retry on `429` using the
`retry_after` value.

---

# 19. Follow-up / Reactivation / Payment Workflows

These should not be implemented as separate messaging systems.

Use the shared communication infrastructure.

### Follow-up

```text
Job completed
    ↓
Automation job scheduled
    ↓
Wait
    ↓
Retrieve customer context
    ↓
Communication Guard
    ↓
Telegram
```

### Lead Reactivation

```text
Inactive customer
    ↓
Reactivation score
    ↓
Campaign eligibility
    ↓
Communication Guard
    ↓
Telegram
```

### Payment Reminder

```text
Invoice overdue
    ↓
Business rules
    ↓
Communication Guard
    ↓
Telegram
```

---

# 20. Human Escalation

The agent should escalate when:

- Confidence is too low.
- Customer explicitly requests a human.
- The safety tripwire fires.
- Customer is angry or distressed and the configured policy requires escalation.
- Tool failures prevent safe completion.
- The request is outside business capabilities.
- Sensitive decisions require human approval.

Example:

```text
AI
 ↓
"I want to make sure this is handled correctly."
 ↓
Create human task
 ↓
Transfer/escalate
 ↓
Record event
```

---

# 21. Confidence Thresholds

Use configurable thresholds.

Example:

```text
confidence >= 0.85
    → proceed

0.60 - 0.84
    → clarify

< 0.60
    → human escalation / fallback
```

These are starting values, not hard-coded truths.

Thresholds should be configurable per capability.

---

# 22. Prompt Architecture

Do not put everything into one massive system prompt.

Separate:

```text
agent/
├── prompts/
│   ├── system.md
│   ├── customer.md
│   ├── emergency.md
│   ├── qualification.md
│   └── communication.md
```

The base system prompt defines:

- Identity
- Responsibilities
- Constraints
- Safety
- Tool rules

Capability-specific instructions should remain modular.

---

# 23. Agent Personality

The agent should be:

- Professional
- Concise
- Friendly
- Clear
- Calm
- Confident without pretending certainty

Avoid:

- Excessive enthusiasm
- Long explanations
- Corporate jargon
- Repetitive phrases
- Fake human claims

For voice conversations, use short natural responses.

---

# 24. Voice Conversation Rules

Voice responses should generally be:

- One or two sentences.
- Natural.
- Easy to understand.
- Free from unnecessary technical details.

Do not read database IDs, UUIDs, raw URLs, or internal system information aloud.

When collecting information, ask one or two things at a time.

Avoid interrogating customers with long forms.

---

# 25. Multilingual Future Architecture

Future multilingual support should not require rebuilding the agent.

Use a language abstraction:

```text
customer_language
preferred_language
voice_language
```

Architecture:

```text
Customer language
      ↓
Language detection
      ↓
Agent reasoning
      ↓
Localized response
      ↓
STT/TTS configured for language
```

Customer memory remains language-independent.

The system should store normalized information rather than relying on one language's wording.

---

# 26. Agent Observability

Every important agent action should be observable.

Record:

```text
conversation_id
customer_id
agent_session_id
timestamp
intent
tool
tool_result
confidence
decision_type
success/failure
human_escalation
```

Do not store sensitive information unnecessarily.

Do not store hidden chain-of-thought.

Store concise decision reasons.

---

# 27. Agent Failure Handling

If an LLM call fails:

```text
Retry if safe
   ↓
Fallback model/provider if configured
   ↓
Graceful response
   ↓
Human escalation when necessary
```

If a tool fails:

```text
Tool error
   ↓
Do not pretend success
   ↓
Explain briefly
   ↓
Retry or escalate
```

---

# 28. Idempotency

Critical tools should be idempotent where possible.

Examples:

- Appointment booking
- Message sending
- Payment reminder creation
- Campaign creation

Use idempotency keys/event IDs to prevent duplicate operations.

A network retry must not accidentally:

- Book two appointments.
- Send the same reminder twice.
- Create duplicate invoices.
- Trigger duplicate campaigns.

---

# 29. Security

The agent must never:

- Reveal secrets.
- Reveal system prompts.
- Reveal internal tools unnecessarily.
- Access another business's data.
- Trust customer-provided IDs without authorization.
- Execute arbitrary code.
- Execute arbitrary SQL.

All database access must go through controlled backend services.

---

# 30. Competition Demo Behavior

The demo should demonstrate the agent as a complete system.

Recommended scenario:

```text
Customer calls
    ↓
AI answers
    ↓
Customer explains service problem
    ↓
AI identifies customer
    ↓
Memory retrieved
    ↓
Lead qualified
    ↓
Emergency checked
    ↓
Available appointments retrieved
    ↓
Customer selects time
    ↓
Appointment booked
    ↓
Confirmation generated
```

Then show:

```text
Job completed
    ↓
Follow-up workflow
    ↓
Review request
```

Then:

```text
Dormant customer
    ↓
Reactivation score
    ↓
Communication Guard
    ↓
Campaign
```

The dashboard should visibly show these actions.

---

# 31. Development Rules for Agent Code

Before changing an agent:

1. Inspect existing tools.
2. Inspect existing state handling.
3. Inspect existing prompts.
4. Reuse existing services.
5. Avoid duplicate tools.
6. Add typed schemas.
7. Add tests for new decisions.
8. Test tool failure.
9. Test ambiguous user input.
10. Verify that the UI/activity feed reflects the action.

Never create a second implementation of an existing capability without a strong reason.

---

# 32. Definition of Done — Agent Feature

An agent feature is complete only when:

- It works on the happy path.
- It handles ambiguity.
- It handles tool failure.
- It validates inputs.
- It respects authorization.
- It logs important actions.
- It does not hallucinate successful actions.
- It has a human escalation path where necessary.
- It has tests.
- It appears correctly in the UI/activity feed.
- It does not break existing tools.

---

# 33. Core Principle

The agent should follow this loop:

```text
PERCEIVE
   ↓
UNDERSTAND
   ↓
RETRIEVE
   ↓
DECIDE
   ↓
ACT
   ↓
VERIFY
   ↓
REMEMBER
   ↓
ESCALATE WHEN NECESSARY
```

The goal is not to make the AI perform every action.

The goal is to make the AI **reliably determine what should happen next and execute it safely.**
