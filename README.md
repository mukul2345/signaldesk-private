# SignalDesk Private

A new, independent repository for a private cash-equity swing research and trading assistant. Its market-data, broker and alert providers will be replaceable independently.

## Current status

Design/configuration baseline only. There is no runnable trading engine, connected live feed, AI service or dashboard here yet. No live orders are enabled. The old trading workspace and hosted scanner are separate reference projects, not dependencies.

## Agreed scope

- ₹50,000 capital ceiling; ₹0–₹1,000/month operating budget; local-first.
- Paper trading and individually approved real orders, gated by broker connectivity, protection and risk tests.
- Approval of a specific live plan may cover its displayed protective stop, partial exits and trailing policy. It does not approve unrestricted automatic entries.
- Operate during exchange market sessions; reconcile at startup. No overnight local monitoring is assumed.
- In-app alerts only in phase 1. WhatsApp, autonomous entries, F&O and public distribution are later milestones.
- Deterministic evidence/risk calculations with optional AI review after evaluation and cost configuration. No profit prediction guarantee.

## Documents

- [Requirements and design](docs/requirements-design.md): full functional requirements, architecture and acceptance criteria.
- [Implementation backlog](docs/implementation-plan.md): work order and gates.
- [Decision record](docs/decisions.md): confirmed choices and unresolved details.
- [Example configuration](config.example.json): proposed settings; not yet consumed by an application.

## Credentials

When the authentication adapter is implemented, copy `.env.example` to `.env` and fill values locally. Do not copy the old environment file wholesale. The example contains no real credentials, PIN or TOTP seed. This repository does not automatically read credentials from its parent directory.

## First implementation milestone

Build normalized market records, explicit risk/configuration validation, a replay-based paper ledger, and provider contracts. Then add Angel One authentication and data ingestion. Establish paper-fill and recovery correctness before implementing approved real orders.

No dependency installation, cloud hosting or paid subscription is required to review this baseline. Runtime setup/run instructions will be added with the first executable milestone.

This is a local Git repository. No remote repository or public deployment has been created.
