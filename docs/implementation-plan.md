# Implementation backlog

Status: proposed work order. This file is not a record of completed features.

## A. Domain and paper foundation

- Define instrument, quote, closed bar, plan revision, approval, risk decision, order, fill, position and alert records, with account and PAPER/LIVE identifiers.
- Define separate market-data, execution-broker, repository and alert interfaces. Declare unsupported capabilities explicitly.
- Implement configuration validation: missing live risk limits, disabled live switch, unknown protection capability or unresolved reconciliation must prevent real execution.
- Add SQLite migrations, immutable events, idempotency keys and a transactional notification outbox.
- Build a recorded-data replay and paper broker with delayed/partial fills, spread, fees, gaps, cancellation and small-quantity TP behavior.
- Implement one versioned swing strategy and comparison fixtures. Expand setup families only after correctness checks.

Exit gate: deterministic replay, no future-data leakage, correct ledger conservation and no live HTTP order calls in paper mode.

## B. Private live data and interface

- Add Angel One owner authentication, session expiry, instrument mapping and live/history adapters.
- Implement exchange-calendar startup/shutdown, prioritized watchlist subscriptions, heartbeat checks, gap recovery and next-startup backfill.
- Build local API and dashboard: source health, candidates, trade plans, paper account, journal and in-app alerts.
- Add entry/TP1/TP2/stop/trailing event processing with revisioned desired and acknowledged stop state.
- Save up to five candidates from completed snapshots, including empty shortlists and exclusions.
- Add institutional evidence incrementally after source access/provenance is verified; never delay basic paper correctness for unavailable feeds.

Exit gate: one complete paper market session, restart/reconnect recovery, snapshot retry checks and visible data-quality failures. A successful session demonstrates operation, not profitability.

## C. Individually approved real orders

- Verify static-IP/account permissions, delivery-sale requirements, permitted order types and overnight protection before implementation acceptance.
- Add broker order/fill queries, submit/cancel/modify and startup reconciliation.
- Add expiring plan-bound approval, actual-fill-based protection and reserved cash/risk accounting.
- Exercise ambiguous submission, partial fills, target/stop races, rejected stop amendments and local downtime without duplicate exposure.
- Add pause-entry and separately confirmed close-position controls.
- Enable a small supervised allowlist only after the owner confirms live risk limits and approves the exact trade plan.

Exit gate: acceptance cases in the requirements pass; broker state matches local state; no unintended real order is sent during tests. If the connectivity/protection prerequisite exceeds budget, retain paper mode and external broker-app execution as the fallback.

## D. Later, separately enabled

- Optional AI evidence review, subject to a selected model, cost ceiling and held-out evaluation.
- WhatsApp adapter with approved templates, delivery status, expiry and costs.
- Private automated entries with explicit strategy/risk activation after evaluation and supervised-live review.
- Alternative licensed data suppliers and broker adapters, tested against normalized replay contracts.
- Multi-user platform only after data-use rights, execution/account isolation, applicable regulatory requirements and operating costs are resolved.
- F&O requires its own specification and validation; it is not a configuration switch in the cash pilot.

## Cost discipline

No paid AI, cloud database, message broker, microservice platform, WhatsApp provider or public hosting is required for milestone A. Measure API load, memory, disk and operating expenses before expanding subscriptions or infrastructure.
