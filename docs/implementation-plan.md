# Implementation backlog

Status: proposed work order. This file is not a record of completed features.

## A. Domain and paper foundation

- Follow requirements section 14: create typed configuration/schema with documented precedence, safe UI projection, injected dependencies and configuration-version snapshots. Test missing/invalid settings, overrides and secret redaction.
- Establish small backend/frontend modules and a composition root; enforce domain-to-infrastructure import boundaries. Put UI styling/motion values in shared design tokens; keep financial formulas exclusively in the backend.

- Implement requirements section 14: typed module-owned configuration, explicit precedence, validation, nonsecret configuration snapshots and safe change semantics. No embedded operational/trading defaults in services.
- Scaffold cohesive backend/frontend feature modules with explicit contracts and dependency injection. Add import-boundary/cycle checks; keep domain code independent of framework, database and broker SDKs.

- Scaffold React/TypeScript/Vite with Tailwind and Motion, and a FastAPI backend; lock dependencies and document local startup. Keep secrets and trading calculations on the backend.
- Freeze the strategy, universe, time-exit and numeric paper-fill contracts from requirements section 13 before implementing formulas. Add positive, negative, gap and insufficient-data fixtures.
- Implement persisted daily equity baselines, cash-flow handling, pending reservations and latched loss locks; test overnight loss and restart behavior.

- Define instrument, quote, closed bar, plan revision, approval, risk decision, order, fill, position and alert records, with account and PAPER/LIVE identifiers.
- Define separate market-data, execution-broker, repository and alert interfaces. Declare unsupported capabilities explicitly.
- Implement configuration validation: missing live risk limits, disabled live switch, unknown protection capability or unresolved reconciliation must prevent real execution.
- Add SQLite migrations, immutable events, idempotency keys, atomic fill/ledger/outbox transactions and a cross-process execution-owner lock. Test duplicate and late fills.
- Build a recorded-data replay and paper broker with delayed/partial fills, spread, fees, gaps, cancellation and small-quantity TP behavior.
- Implement one versioned swing strategy and comparison fixtures. Expand setup families only after correctness checks.

Exit gate: deterministic replay, no future-data leakage, correct ledger conservation and no live HTTP order calls in paper mode.

## B. Private live data and interface

- Completed: official NSE EOD provider, official Nifty 500 candidate synchronization with validation, and a versioned NSE cash-market calendar used by the scheduler.
- Completed: staged, resumable history warm-up with persisted progress, per-symbol failure isolation, API controls and visible activation readiness.
- Completed: official NSE corporate-action evidence, configurable price-continuity checks, a no-bypass promotion gate, recoverable previous-universe backup and restart-bound activation.
- Completed: immutable raw-history preservation plus deterministic adjusted views for parseable bonus and face-value ratios. Rights issues, demergers, future actions and unparseable events remain fail-closed.
- Next: add a licensed or verified adjusted-history source for unsupported corporate actions, then complete and validate the 496-symbol warm-up.
- Add Angel One owner authentication, session expiry, instrument mapping and live/history adapters.
- Implement exchange-calendar startup/shutdown, prioritized watchlist subscriptions, heartbeat checks, gap recovery and next-startup backfill.
- Build local API and dashboard: source health, candidates, trade plans, paper account, journal and in-app alerts. Add durable WebSocket event replay, incomplete-scan states, daily index changes, keyboard navigation and reduced-motion support.
- Add entry/TP1/TP2/stop/trailing event processing with revisioned desired and acknowledged stop state.
- Save up to five candidates from completed snapshots, including empty shortlists and exclusions.
- Add institutional evidence incrementally after source access/provenance is verified; never delay basic paper correctness for unavailable feeds.

Exit gate: one complete paper market session, restart/reconnect recovery, snapshot retry checks and visible data-quality failures. A successful session demonstrates operation, not profitability.

## C. Individually approved real orders

- Verify static-IP/account permissions, delivery-sale requirements, permitted order types and overnight protection before implementation acceptance.
- Add broker order/fill queries, submit/cancel/modify and startup reconciliation.
- Add expiring plan-bound approval, actual-fill-based protection and reserved cash/risk accounting.
- Exercise ambiguous submission, partial fills, target/stop races, rejected stop amendments and local downtime without duplicate exposure.
- Add pause-entry and separately confirmed close-position controls. Gate new entries on dashboard supervision without cancelling protection on disconnect.
- Enable a small supervised allowlist only after the owner confirms live risk limits and approves the exact trade plan.

Exit gate: acceptance cases in the requirements pass; broker state matches local state; no unintended real order is sent during tests. If the connectivity/protection prerequisite exceeds budget, retain paper mode and external broker-app execution as the fallback.

Before milestone C, the live-paper evidence report must reach its configured minimum closed-trade sample and pass the drawdown gate. A target return being observed in one month is not sufficient evidence and never enables orders automatically.

## D. Later, separately enabled

- Optional AI evidence review, subject to a selected model, cost ceiling and held-out evaluation.
- WhatsApp adapter with approved templates, delivery status, expiry and costs.
- Private automated entries with explicit strategy/risk activation after evaluation and supervised-live review.
- Alternative licensed data suppliers and broker adapters, tested against normalized replay contracts.
- Multi-user platform only after data-use rights, execution/account isolation, applicable regulatory requirements and operating costs are resolved.
- F&O requires its own specification and validation; it is not a configuration switch in the cash pilot.

## Cost discipline

No paid AI, cloud database, message broker, microservice platform, WhatsApp provider or public hosting is required for milestone A. Measure API load, memory, disk and operating expenses before expanding subscriptions or infrastructure.

## Vercel release gate

- Static frontend build: technically ready, but not useful alone.
- Private local paper pilot: current supported runtime.
- Functional private cloud release: blocked on durable database/storage, authenticated scheduled jobs, production secrets/authentication, complete adjusted history and staging recovery evidence.
- Approved real orders and public/multi-user access are later gates and are not part of the first Vercel deployment.
