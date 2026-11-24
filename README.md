# SignalDesk Private

> Cloud migration status: the zero-cost Supabase/Vercel foundation is in progress.
> See [docs/zero-cost-cloud-deployment.md](docs/zero-cost-cloud-deployment.md).

A new, independent repository for a private cash-equity swing research and trading assistant. Its market-data, broker and alert providers will be replaceable independently.

## Current status

The runnable paper-mode workflow now includes the React/TypeScript/Vite frontend, FastAPI service, validated configuration, SQLite ledger, deterministic entry and exit replay, durable completed-scan history, an automatic local scan scheduler, a Settings & Health control plane, and a versioned deterministic daily-breakout engine. The strategy uses completed daily bars only, enforces warm-up and chronological data, calculates SMA trend, prior-range breakout, volume confirmation, ATR risk levels, permitted entry extension, R targets and a 15-session time exit. It returns READY/WATCH/AVOID/INSUFFICIENT with evidence rather than an invented probability. Fully covered snapshots can archive up to the configured number of eligible setups using an idempotent slot key; incomplete coverage is rejected.

The default research provider is now the official NSE bhavcopy MCP. It retrieves up to three months of completed daily OHLCV history, refreshes the latest session in batches, incorporates official benchmark and market-breadth evidence, and caches it locally. The active pilot universe contains five symbols in `backend/data/nse-universe.json`. A separate synchronizer validates the official Nifty 500 constituent CSV and writes an inactive candidate file. Settings & Health provides a staged history warm-up control that retrieves five symbols per batch, persists each successful batch and isolates failures for retry. A separate fail-closed promotion gate checks constituent count, complete history, latest-session alignment, official NSE corporate actions and configured price-discontinuity limits. Bonus and face-value changes with parseable NSE ratios are applied to an in-memory adjusted view while the raw cache remains immutable. Rights issues, demergers and unparseable events require an authoritative adjusted-price source and remain blocked. Promotion writes a recoverable previous-universe backup and requires an API restart; no override bypass is exposed. The configured EOD scan runs at 18:30 Asia/Kolkata after the data cutoff and consults the versioned NSE cash-market calendar rather than treating every weekday as a session. The project does not yet contain an external adjusted-price source, AI service or a live order path. No live orders are enabled.

## Run the design

Requirements: Node.js 20 or newer and Python 3.9 or newer.

```bash
npm install
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm run api
```

In a second terminal:

```bash
npm run dev
```

Open the local URL printed by Vite. Use `npm run build` for a production build and type check. Run backend tests with `npm run test:api`.

## Daily MVP workflow

Keep the API running during the local pilot. It automatically runs the completed-candle scan at the configured 18:30 Asia/Kolkata exchange-session slot. Open the bell in the top bar to see the latest persistent daily brief: up to five READY/WATCH setups with entry, SL, TP1 and TP2, plus portfolio value, P&L, concentration, reserved risk and stop health.

To run the same idempotent workflow manually while the API is running:

```bash
npm run mvp:run
```

The command prints the actionable shortlist and portfolio summary in the terminal. A legitimate zero-setup day is reported as zero; the scanner does not relax its policy to manufacture five trades. The current active pilot scans five symbols. The validated Nifty 500 candidate remains inactive until its history and promotion gates are complete.

The alert drawer also contains a **Live paper evidence** gate. It calculates win rate, net and average P&L, maximum drawdown and rolling 30-day return only from closed paper positions observed during forward testing. The configured 30% monthly value is an evaluation threshold, never a prediction. Status remains `INSUFFICIENT_EVIDENCE` until at least 30 paper trades have closed, and it fails the risk gate when observed drawdown exceeds policy.

To download and validate the latest official Nifty 500 constituents without activating them:

```bash
npm run sync:nse-universe
```

The command requires network access and writes `state/nifty-500-universe-candidate.json`, which is ignored by Git. It accepts only `EQ` rows, requires unique valid symbols and rejects downloads outside the configured 490–510 count envelope. Open **Settings & health → Nifty 500 history warm-up** to process the candidate in resumable batches. Do not point the active `universe_path` at this candidate until the panel reports that every symbol is ready.

Trading values come from [backend/config.default.json](backend/config.default.json), the research-provider payload and typed frontend configuration. The API validates configuration at startup, rejects live mode, and stores paper orders in the ignored local `state/` directory. Components do not own risk or market constants.

## Agreed scope

- ₹50,000 capital ceiling; ₹0–₹1,000/month operating budget; local-first.
- Paper trading and individually approved real orders, gated by broker connectivity, protection and risk tests.
- Approval of a specific live plan may cover its displayed protective stop, partial exits and trailing policy. It does not approve unrestricted automatic entries.
- Operate during exchange market sessions; reconcile at startup. No overnight local monitoring is assumed.
- In-app alerts only in phase 1. WhatsApp, autonomous entries, F&O and public distribution are later milestones.
- Deterministic evidence/risk calculations with optional AI review after evaluation and cost configuration. No profit prediction guarantee.

## Documents

- [Readiness review](docs/implementation-readiness-review.md): critical gaps, resolved design ambiguities and remaining release gates.
- [Requirements and design](docs/requirements-design.md): full functional requirements, architecture and acceptance criteria.
- [Implementation backlog](docs/implementation-plan.md): work order and gates.
- [Decision record](docs/decisions.md): confirmed choices and unresolved details.
- [Example configuration](config.example.json): a documented copy of the configurable policy and provider settings.

## Market data and credentials

No Angel One credentials are required for the default NSE EOD research workflow. The official NSE MCP is intended for informational, educational and non-commercial use. It supplies completed EOD data and near-live summaries, not exchange-grade ticks, order-book depth or an order-execution channel. Review the [official NSE MCP page](https://www.nseindia.com/nse-mcp) and its current terms before changing the usage model.

The Angel One adapter remains available as an optional future personal-account provider. Copy `.env.example` to `.env` and supply `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PIN`, `ANGEL_TOTP_SECRET` and the network identity registered for the SmartAPI application. Do not copy an existing environment file wholesale. The application reports only missing variable names; it never returns credential values.

Copy `backend/data/angel-one-instruments.example.json` into the ignored `state/` directory, replace every placeholder with a current Angel One symbol token, and point `angel_one.instruments_path` at that file. Then change `providers.market_data` from `nse_mcp` to `angel_one` in `backend/config.default.json` and restart the API. If authentication, tokens or candle retrieval fail, the scan fails closed.

## Deployment readiness

The private paper MVP is packaged as one authenticated production container. It serves the compiled frontend and API from one origin, writes the ledger and caches to a mounted `/data` volume, keeps the EOD scheduler alive and resumes Nifty 500 warm-up automatically. The service fails startup when production persistence or authentication is missing. See the [deployment runbook](docs/deployment.md).

The tracked Vercel configuration is suitable for a static frontend preview only. The supported functional deployment uses a long-running container with a persistent disk because this release intentionally retains SQLite/WAL and an in-process scheduler to stay within the private pilot budget. Real orders remain disabled.

## First implementation milestone

The frontend and API now cover official NSE EOD strategy scanning, paper trade plans, account replay, scan history, exchange-session-aware scheduling, health, configuration, validated Nifty 500 candidate generation, staged resumable history warm-up, deterministic split/bonus adjustment and guarded promotion. The current local candidate has 496 symbols; its persisted progress and every activation gate are visible in Settings & Health. Unsupported corporate actions must be reconciled from an authoritative adjusted-price source before promotion. Establish complete coverage and recovery correctness before activating the broader universe, implementing approved real orders or relying on a broker connection.

No cloud hosting or paid subscription is required to run the design locally.

This is a local Git repository. No remote repository or public deployment has been created.
