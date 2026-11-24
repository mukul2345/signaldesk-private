# Implementation readiness review

Reviewed 14 November 2026 against requirements v0.2, configuration and backlog; resulting baseline v0.3. This is a design review, not a code audit, broker certification or strategy-performance test. No executable application exists in this repository yet.

## Verdict

Ready to start milestone A foundation work. Not ready to implement unspecified trading formulas, claim predictive accuracy or enable live orders. Deliver the paper pilot independently of broker execution eligibility. The engineering gaps below now have requirements; their controls remain unimplemented until tested.

## Critical gates still open

1. **Executable strategy contract — implementation owner, milestone A.** Formula/warm-up, entry band/expiry, time exit and ranking are not yet selected. Different implementations could otherwise produce different trades from the same data. Freeze one paper hypothesis and expected fixtures before writing the signal engine. See requirements section 13, Strategy contract.
2. **Broker protection and account eligibility — adapter verification with owner, before milestone C.** Document supported authorisation, connectivity, overnight validity and target/stop behavior. Two independently placed sell orders can race; a local quantity check is not an atomic broker guarantee. Require capability evidence and fault tests or retain paper/external execution only. O2/O6 remain open; this review did not reverify current broker terms.
3. **Actual live risk and emergency policy — owner, before milestone C.** ₹50,000 is a capital ceiling, not agreed acceptable loss. Per-trade, daily, aggregate, position/count limits and bounded emergency actions need explicit live approval. Configuration now leaves all live position limits unset rather than inheriting paper defaults. O1 remains open.

## Important gaps resolved in the specification

- **Accounting ambiguity:** defined capital ceiling versus broker funds, pending reservations, previous-session equity baseline, overnight losses, cash-flow adjustment and a daily lock that survives restart. Implementation must prove conservation and baseline fixtures.
- **Alert expectations:** in-app alerts cannot promise immediate delivery with the tab closed. Added supervised entry gating, durable event replay and preservation of protection on disconnect.
- **Inconsistent fresh-repo architecture:** removed assumptions that old D1 routes, Docker runtime or parent credentials are dependencies. Recorded React/TypeScript/Vite, FastAPI, SQLite, Tailwind and Motion with reproducible dependency setup.
- **Scan semantics:** made coverage/exclusions explicit; incomplete runs cannot replace an actionable shortlist. Top 50/top five are maxima, not quotas. Daily strategies use completed candles; historical setup observations are deduplicated for evaluation.
- **Recovery holes:** required atomic fill/ledger/outbox writes, late-fill handling, cross-process execution ownership, subscription priority and bounded scan work.
- **Product trust:** documented daily index comparison, missing evidence, replay badges, reduced motion and stable order-confirmation UI. No synthetic probability is acceptable.
- **Simulation validity:** numeric fill/fee assumptions and outcome horizon must be frozen; corporate actions, gaps and halts require tests. Daily-bar replay is separate from live-observation paper results.

## Work sequence

1. Scaffold the selected stack and validated configuration, then implement domain records, migration and replay fixtures.
2. Freeze the strategy and paper-fill contracts; implement and test risk/ledger conservation before connecting execution.
3. Verify data access/history/calendar coverage, then build the live-data paper UI and one-session recovery demonstration.
4. Collect prospective results. Add live orders only after the separate owner/broker gates pass; never enable them to finish a UI demo.

No additional paid infrastructure or AI subscription is required to begin. Data access, strategy edge and supported real execution remain things to establish, not assumed capabilities. Twelve-month audit retention remains a proposed local policy; 30-day shortlist display is already agreed.
