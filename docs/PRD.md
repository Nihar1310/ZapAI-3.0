Product Requirements Document (PRD)
Product: ZapAI v2 – “Preview → Pay → Enrich”
Author / PM: ChatGPT (acting PM)
Revision Date: 14 July 2025 (incorporates pricing, preview-scope and bulk-CSV decisions)
Status: Draft for stakeholder sign-off

⸻

1 · Background & Vision

ZapAI currently meta-searches Google/Bing, scrapes results, runs in-house LLM extraction and returns structured contacts. The pivot introduces a freemium funnel:

Stage	Tech	Value to user	Revenue trigger
Preview	Firecrawl /search	Fast meta-search + one masked email per domain (teaser)	Free
Checkout	Stripe Checkout	Hosted payment flow (pay-per-unlock)	User pays for this search_id
Enrichment	Apollo.io bulk endpoints	Full emails, phones, LinkedIn, firmographics	Delivered post-payment

Firecrawl replaces the custom Playwright+regex pipeline for preview; Apollo remains the authoritative enrichment engine.

⸻

2 · Objectives & Success Metrics

Objective	KPI	Target
Faster time-to-preview	p95 preview latency	≤ 4 s (was ~9 s)
Lower infra cost	LLM token spend	–30 % (Firecrawl first-pass)
Conversion	Preview→Checkout click-through	≥ 15 %
Revenue	Avg. checkout value	≥ US $3 per unlock
Reliability	End-to-end success rate	≥ 99.5 %


⸻

3 · Target Users & Personas
	•	Growth Marketer Maya – scrapes niche SMB contacts for campaigns.
	•	Sales Ops Omar – enriches CRM leads ad-hoc.
	•	Founder Farah – validates market potential quickly.

⸻

4 · High-Level User Journey

sequenceDiagram
  participant User
  participant API as ZapAI API
  participant FC as Firecrawl
  participant ST as Stripe
  participant WK as Worker
  participant AP as Apollo
  User->>API: POST /search?q="cardiologist nyc"
  API->>FC: /search
  FC-->>API: Links + masked e-mail + snippet
  API-->>User: Preview JSON
  User->>API: POST /search/{id}/checkout
  API->>ST: Create CheckoutSession (metadata: search_id)
  ST-->>User: Hosted payment page
  ST-->>API: webhook checkout.session.completed
  API->>WK: enqueue EnrichJob(search_id)
  WK->>AP: people/bulk_match (batched)
  AP-->>WK: Enriched contacts
  WK->>API: mark status=ready
  User->>API: GET /search/{id}?full=true
  API-->>User: Full contact list


⸻

5 · Scope & Out-of-Scope

In scope (v2)	Out of scope (later)
Free preview with masked email	Bulk CSV upload workflow
Stripe pay-per-unlock	Subscription or credit bundles
Firecrawl integration (cloud API)	Self-hosting Firecrawl core (AGPL)
Celery/Dramatiq job queue	Advanced lead deduplication / CRM push

Bulk CSV upload will be revisited in Q4 2025 after revenue validation; discovery tasks begin now (see §13).

⸻

6 · Functional Requirements

Ref	Requirement	Priority
FR-1	Preview Search – Call Firecrawl /search (10 results). For each domain, store first email then expose one masked email (m•••@ac••.com).	P0
FR-2	Checkout Endpoint – POST /search/{id}/checkout → returns Stripe Checkout URL (pay-per-unlock).	P0
FR-3	Stripe Webhook – Verify signature; idempotently mark payments.status=paid, flip search.status=paid, enqueue enrichment job.	P0
FR-4	Enrichment Worker – Batched Apollo people/bulk_match calls (≤10 /request); populate contacts.	P0
FR-5	Polling / WS – GET /search/{id}?full=true returns 202 until status =ready; WS pushes progress.	P1
FR-6	Feature Flag USE_FIRECRAWL – graceful fallback to legacy scraper on 5xx or quota breach.	P0
FR-7	Cost Tracker – Record Firecrawl credit units, Apollo cost, Stripe fees per search_id.	P1
FR-8	Rate Limiting – Redis token bucket keyed (user_id, plan) aligned with Firecrawl global limits.	P1
FR-9	Masked-Email Formatter – Utility to keep first char of local & domain, mask rest; ensure GDPR compliance.	P0


⸻

7 · Non-Functional Requirements

Area	Requirement
Performance	p95 preview ≤ 4 s; enrichment job queued < 5 s after payment
Scalability	Horizontal worker autoscale (Kubernetes / Docker Compose)
Reliability	Circuit-breaker around Firecrawl; retry w/ exponential back-off (max 3)
Security	PII encrypted at rest; no card storage; SOC-2 readiness
Observability	OpenTelemetry traces from /search to worker; Prometheus + Grafana dashboards
Compliance	GDPR/India DPDP delete endpoint; Apollo TOS review
Licensing	Hosted Firecrawl avoids AGPL; if self-hosting MCP server (MIT) publish changes as required


⸻

8 · Data Model Changes (PostgreSQL via Alembic)

Table	New / Modified Fields
payments (NEW)	id, user_id, search_id, stripe_session_id, amount, status ENUM(pending,paid,failed), timestamps
search_queries	+ status ENUM(preview,paid,enriching,ready,failed)+ firecrawl_raw JSONB
contacts	unchanged (populated post-enrichment)
costs (NEW)	id, search_id, firecrawl_cost, apollo_cost, stripe_fee


⸻

9 · API Contract (v1)

Endpoint	Method	Description
/api/v1/search	POST	Create preview; body {query}
/api/v1/search/{id}	GET	Returns preview or full, controlled by ?full=true
/api/v1/search/{id}/checkout	POST	Returns Stripe Checkout URL
/api/v1/stripe/webhook	POST	Receives Stripe events (no auth)

OpenAPI YAML will be version-bumped but path stays v1 to avoid client breakage.

⸻

10 · Architecture & Engineering Tasks

ID	Task	Owner	Effort	Key Files / Components
T-1	Firecrawl client wrapper + feature flag	BE	1 d	services/firecrawl_client.py
T-2	Orchestrator refactor (replace scraper, add masking util)	BE	1 d	search_orchestrator.py, utils/mask.py
T-3	Stripe service & routes	BE	1.5 d	api/v1/payments.py, services/payment_service.py
T-4	DB migrations (Alembic)	BE	0.5 d	alembic/versions
T-5	Celery/Dramatiq worker for Apollo	BE	2 d	worker/enrichment_worker.py
T-6	Cost tracker update	BE	0.5 d	services/cost_tracker.py
T-7	Observability stack (OTel + dashboards)	DevOps	1 d	docker-compose.yml, otel-collector.yaml
T-8	Docs & runbooks	PM/BE	0.5 d	README, PROJECT_STATUS.md
T-9	Canary & feature-flag rollout scripts	DevOps	1 d	scripts/canary.sh

Total development estimate: ~8 developer-days.

⸻

11 · Roll-Out Plan

Date (T=Kick-off)	Milestone	Exit Criteria
T + 5 d	Dev complete	All tasks merged, tests green
T + 6 d	Staging deploy	Stripe test payments flow works; p95 preview ≤ 4 s
T + 7 d	Canary (10 %)	Error rate < 2 %; cost within ±10 % forecast
T + 10 d	Full production	Docs updated; on-call runbook signed
T + 14 d	Post-launch review	KPIs: ≥ 15 % conversion, latency SLA met


⸻

12 · Risks & Mitigations

Risk	Mitigation
Firecrawl quota/downtime	Toggle to legacy scraper (USE_FIRECRAWL=false); display “temporarily limited” banner
Apollo rate limit or cost spike	Back-off in worker; pre-payment quota check; investigate Clearbit fallback
Webhook loss	Idempotent DB updates; hourly reconciliation job for paid but not ready
Data privacy	Masked email in preview; hashed emails in logs; “Delete my data” endpoint
AGPL exposure (self-hosting)	Start with hosted Firecrawl; if MCP self-host, open-source patches


⸻

13 · Deferred Feature – Bulk CSV Uploads (Q4 2025)

Discovery Task	Owner	Target
Track user asks for bulk via Intercom	PM	Live day 1
Collect sample CSVs & volumes	PM	End of sprint
Spike: S3 presigned upload + worker fan-out	BE	Q3 backlog
Business model	PM	Decide credit bundles vs. subscription

Progress will be re-evaluated at the Q3 OKR review.

⸻

14 · Post-Approval Checklist
	•	Sign-off from Engineering Lead
	•	Legal review (Apollo & Firecrawl licences, GDPR wording)
	•	Stripe test mode credentials configured in CI
	•	Front-end team receives new OpenAPI spec & masking UI guidelines

⸻

Appendix – Key External Docs
	•	Firecrawl Search & Pricing docs
	•	Firecrawl MCP server (MIT) repo
	•	Apollo Bulk People Enrichment API
	•	Stripe Checkout Session & Webhook guides

⸻
