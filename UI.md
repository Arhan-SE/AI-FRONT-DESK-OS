# UI/UX Specification — AI Business Operating System

## 1. Design Direction

The interface should feel like a premium, minimal enterprise operations console.

### Core principles

- Black, white, and neutral grayscale only.
- No gradients.
- No unnecessary illustrations.
- No excessive rounded cards.
- No visual clutter.
- Strong typography and spacing.
- Every screen should have a clear primary action.
- Prefer information density through typography, tables, status indicators, and whitespace rather than decorative UI.
- Desktop-first for the competition demonstration, responsive where practical.
- Accessibility and keyboard navigation should be considered from the beginning.

## 2. Visual System

### Colors

Grayscale only, using a slightly cool neutral. Pure zero-saturation gray reads as
flat; a trace of blue gives depth while still reading as monochrome.

```css
--bg              220 20% 99%    /* near-white page background      */
--surface         220 14% 97%    /* sidebar, table headers          */
--surface-raised  0   0%  100%   /* cards, popovers                 */
--border          220 13% 91%    /* hairlines — the main structure  */
--border-strong   220 13% 84%    /* emphasis dividers               */
--fg              220 20% 10%    /* near-black, never pure #000     */
--fg-muted        220  9% 46%    /* secondary text                  */
--fg-subtle       220  9% 60%    /* metadata, timestamps            */
--accent          220 20% 10%    /* primary buttons                 */
--accent-fg       0   0%  100%
--focus           220 20% 10%    /* 2px ring, always visible        */
```

Status colors are the only color in the product and carry meaning only:

```css
--critical  0   72% 45%   /* emergency HIGH        */
--warning   38  92% 42%   /* overdue, needs review */
--success   142 55% 33%   /* completed, delivered  */
```

Status appears as a small dot or a thin left border, never as a filled bright
pill. Because everything else is gray, one red edge is impossible to miss.

### Typography

Self-host the fonts. Do not load from a CDN.

- **Geist Sans** — interface, headings, body.
- **Geist Mono** — metrics, timestamps, IDs, confidence values, table numerics.

Numeric data must use tabular figures so values do not shift as they update.

| Role          | Size | Weight | Notes            |
| ------------- | ---- | ------ | ---------------- |
| Page title    | 24px | 600    | -0.02em tracking |
| Section title | 15px | 600    | -0.01em tracking |
| Metric        | 32px | 600    | tabular numerals |
| Body          | 14px | 400    |                  |
| Table cell    | 13px | 400    | tabular numerals |
| Label         | 12px | 500    | muted            |
| Metadata      | 12px | 400    | mono, subtle     |

Avoid oversized marketing-style headings inside the application.

### Shape and depth

- Radii: 4px default, 6px cards, 8px maximum. Never fully rounded cards.
- No shadows on cards. Structure comes from hairline borders.
- One soft shadow, reserved for popovers and dialogs.
- Table rows 40px. Generous spacing between sections, compact within data.
- Motion: 120-150ms opacity and transform only.

### Anti-patterns

The interface must not look machine-generated. Specifically avoid:

- Gradients, especially purple or blue.
- Large rounded cards with drop shadows.
- Emoji in headings or navigation.
- Cards where a table would carry the data better.
- Bright filled status pills.
- Centered hero text inside the application.
- A single font weight used everywhere with no hierarchy.

### Spacing

Use a consistent spacing scale based on Tailwind's spacing system.

Prioritize generous whitespace around major sections while keeping tables and operational data compact.

## 3. Application Shell

The application should use a persistent left sidebar on desktop.

### Navigation

- Overview
- AI Activity
- Leads
- Customers
- Appointments
- Conversations
- Campaigns
- Reviews
- Payments
- Insights
- Settings

The sidebar should remain visually quiet. The active page is indicated through subtle contrast rather than bright colors.

## 4. Dashboard

The Overview page should answer:

> "What is happening in my business right now?"

### Top metrics

- Leads
- Appointments
- Jobs
- Outstanding payments
- Reviews
- Reactivation opportunities

### Attention section

Show only items requiring action:

- High-value lead awaiting follow-up
- Potential emergency
- Overdue payment
- Appointment issue
- Failed campaign
- Human approval required

### AI activity

Display a live operational feed:

```text
10:42:31  Incoming customer conversation
10:42:34  Customer identified
10:42:36  Intent detected: Boiler repair
10:42:38  Emergency probability: 8%
10:42:40  Lead score: 87/100
10:42:43  Appointment availability checked
10:42:45  Appointment booked
10:42:46  Confirmation sent
```

This feed is a key part of the competition demonstration.

## 5. AI Activity Page

This should be one of the strongest screens.

Show:

- Current AI tasks
- Completed tasks
- Human escalations
- AI confidence
- Tool calls
- Workflow status
- Recent decisions

Each event should have:

- Timestamp
- Event type
- Customer/business context
- AI decision
- Confidence
- Result

## 6. Leads

Use a clean table rather than large cards.

Columns:

- Customer
- Service
- Lead score
- Priority
- Status
- Last contact
- Next action

Lead score should be visually prominent but still monochrome by default.

Lead details should show:

- Original conversation
- Extracted information
- Qualification reasoning
- Score breakdown
- Customer history
- Recommended action
- Human override option

## 7. Customers

Customer profile should act as a unified customer record.

Sections:

- Contact information
- Communication preferences
- Service history
- Appointments
- Payments
- Reviews
- Conversations
- AI-generated customer summary
- Long-term memory

The customer page should make the memory system visible and understandable.

## 8. Appointments

Use a clean calendar/list hybrid.

Show:

- Date
- Time
- Customer
- Service
- Technician
- Status
- Reminder status

Appointment details should expose:

- Booking source
- Customer context
- Reminder history
- Follow-up status

## 9. Conversations

Use a two-panel layout:

Left:
- Conversation list
- Customer
- Channel
- Status
- Last activity

Right:
- Conversation
- Customer context
- Relevant memory
- AI actions
- Human takeover

The interface should clearly distinguish AI-generated messages from human messages without relying on bright colors.

## 10. Campaigns

Campaign dashboard should include:

- Active campaigns
- Scheduled campaigns
- Completed campaigns
- Audience size
- Sent
- Delivered
- Replies
- Opt-outs
- Conversion/result

Campaign examples:

- Lead reactivation
- Seasonal service reminder
- Review request
- Payment reminder

## 11. Payments

Show:

- Outstanding
- Due soon
- Paid
- Overdue

Each invoice should expose:

- Customer
- Amount
- Due date
- Status
- Reminder history
- Next reminder

No real payment processing is required for the competition demonstration unless specifically implemented.

## 12. Insights

This page should focus on business intelligence.

Examples:

- Lead conversion rate
- Average response time
- Appointment conversion
- Reactivation rate
- Follow-up completion
- AI automation rate
- Human intervention rate
- Potential recovered revenue

Use simple charts with minimal decoration.

## 13. AI Administrative Manager

This should eventually become a dedicated AI command interface.

Example:

User:

> How is my business doing?

AI:

> You received 127 leads this month. 84 appointments were booked. 7 high-value leads have not been followed up. 31 customers appear eligible for seasonal reactivation.

The response should link directly to relevant records/actions.

## 14. Design Components

Use reusable components instead of one-off UI implementations.

Core components:

- Button
- Input
- Select
- Dialog
- Drawer
- Table
- Badge
- Tabs
- Dropdown
- Tooltip
- Toast
- Skeleton
- Empty state
- Error state
- Confirmation dialog
- Pagination
- Search
- Command menu

Prefer shadcn/ui primitives and customize them to the monochrome design system.

## 15. UX Rules

- Never hide important actions behind unnecessary menus.
- Never use a modal when inline editing is sufficient.
- Confirm destructive actions.
- Show loading states.
- Show empty states.
- Show API/network errors clearly.
- Never silently fail.
- Preserve user input when requests fail.
- Use optimistic UI only for operations that can safely be rolled back.
- Disable duplicate submissions.
- Always show the current system state.
- Avoid excessive animations.

## 16. Reliability Rules

The UI must be designed around real asynchronous systems.

Every API request should have:

- Loading state
- Success state
- Error state
- Retry option where appropriate

Every AI action should have:

- Status
- Timestamp
- Result
- Error/failure reason when applicable

Do not expose raw stack traces to users.

## 17. Competition Demo Mode

Include a dedicated demo environment.

### Live voice call

The voice demo runs **in the browser**, never in a terminal.

A dedicated page provides a two-panel layout:

Left:
- Start / end call control
- Microphone state
- Thin waveform while speaking
- Live transcript, AI turns distinguished from customer turns

Right:
- The AI Activity feed, streaming in real time as the conversation happens

Watching a decision appear on the right while the customer is still speaking on
the left is the single most important thing this interface does.

Build the call UI from scratch against the LiveKit client SDK. Do not import the
SDK's default component styles; they do not match this design system.

Connection states must all be visible and never silent: requesting microphone,
connecting, connected, agent joined, reconnecting, ended, failed.

### Scenarios

The demo should allow the team to trigger predefined scenarios:

1. Normal customer inquiry
2. High-value lead
3. Appointment booking
4. Completed job → follow-up
5. Overdue payment → reminder
6. Dormant customer → reactivation

Each scenario should produce visible AI activity in real time.

Emergency scenarios are out of scope for this version.

## 18. Performance

- Lazy-load heavy pages/components.
- Avoid unnecessary polling.
- Use server-side pagination for large tables.
- Debounce search inputs.
- Cache safe read-heavy data.
- Keep animations minimal.
- Avoid unnecessary client-side state duplication.

## 19. Final Visual Goal

The UI should communicate:

> "This is an AI command center for a real business."

It should not communicate:

> "This is a school project with lots of AI features."

The strongest visual elements should be:

- Typography
- Whitespace
- Data
- Live AI activity
- Clear hierarchy
- Consistent interaction patterns

Avoid decorative complexity.
