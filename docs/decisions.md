# Decision record

Recorded 14 November 2026. These decisions supersede the earlier project's draft for work in this repository.

## Confirmed

1. Start in a new independent local repository; preserve the old code as reference.
2. Personal use with Angel One first, with replaceable data and execution adapters.
3. Capital ceiling ₹50,000. Operating-cost ceiling ₹1,000/month, local-first.
4. Start with cash-equity swing trading, paper trading and individually approved real orders.
5. An approved plan may include automated protective orders, partial exits and trailing updates. Approval binds to the displayed policy and revision. New automated entries remain deferred.
6. Run during exchange market sessions, with startup reconciliation and no reliance on overnight local processing.
7. In-app alerts only in phase 1. No WhatsApp account, messaging fee or integration is required now.

## Proposed, not confirmed live settings

- Risk per trade 0.5%, daily equity-loss entry lock 1.5%, aggregate initial open risk 2%.
- At ₹50,000 starting equity these correspond to ₹250, ₹750 and ₹1,000. They are not guaranteed maximum losses.
- TP1/TP2 at 1R/2R, 50/50 exits, completed-daily ATR trailing. The owner's latest response did not explicitly confirm these numerical parameters; treat them as paper-test hypotheses.
- A 12-month private audit ledger, with a 30-day visible shortlist and bounded raw-data retention.

## Implementation dependencies

- Supported authentication, verified session behavior and account-specific static-IP/API permissions.
- Broker-held overnight protective-order validity and delivery-sale authorisation.
- Approved numerical live risk limits and a tested emergency workflow before live arming.
- A selected, versioned strategy and realistic replay tests before performance claims.

## AI and institutional-data boundary

An AI model can review supplied evidence and estimate conditional outcomes. It cannot determine future profit with certainty. Agent skills are workflows, not proof of data access or predictive performance.

FII/DII market-wide flows, company ownership disclosures, disclosed deals and price/volume pressure estimates are distinct data sources with different publication delays and coverage. None is treated as a complete live map of named institutions' stock purchases. Source timestamps, missing data and revisions must remain visible. AI-generated explanations cannot fill factual gaps.

No market feed or model endpoint is connected in this new repository yet. Future AI evaluation compares held-out net performance and calibration with the deterministic baseline, including costs, losses and unresolved trades.

## Engineering decisions from the requirements review

Using the owner's delegated technical authority: FastAPI + SQLite backend; React/TypeScript/Vite + Tailwind + Motion frontend; same-origin local serving and recoverable WebSocket events. Build fresh with no dependency on the old deployment or parent credentials.

Requirements v0.3 section 13 defines scan coverage, risk accounting, atomic event processing, subscription priority and supervised live entry behavior. These are implementation requirements, not completed controls. All numerical live limits remain unset. Strategy formulas, paper fill assumptions and holding-period expiry must be frozen before their engine implementation; broker capability verification and owner risk approval gate real orders.

## Owner requirement: configurable micro-modules

All business/operational values must come from validated, versioned configuration; secrets remain server-side. Small responsibility-focused modules with explicit interfaces and dependency injection form one local modular application. Mathematical/protocol constants and mandatory safety invariants remain named code definitions, not editable trading settings. Requirements v0.4 section 14 defines configuration ownership, module boundaries and acceptance checks. These requirements are recorded; enforcement will be built with the application.

## Owner requirement — 15 November 2026

No hardcoded configurable business or operational values. Use a validated central configuration contract, injected settings, versioned plan snapshots and shared UI design tokens. Keep secrets separate. Named mathematical/protocol constants and test fixtures are permitted; live limits cannot default silently.

Build small cohesive modules with explicit interfaces and enforced dependency direction. Use a modular application initially, not a fleet of microservices. Requirements section 14 defines backend/frontend boundaries and verification criteria.
