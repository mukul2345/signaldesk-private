from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from signaldesk.application.strategy_scanner import StrategyResearchProvider
from signaldesk.config import load_settings
from signaldesk.infrastructure.market_data_factory import build_daily_bar_provider
from signaldesk.infrastructure.supabase_rest import SupabaseRest
from signaldesk.infrastructure.telegram import TelegramBot


def _owner_id() -> str:
    value = os.environ.get("SIGNALDESK_OWNER_ID", "")
    if not value:
        raise RuntimeError("SIGNALDESK_OWNER_ID is required")
    return value


def run_daily_scan(client: SupabaseRest) -> dict[str, Any]:
    settings = load_settings()
    research = StrategyResearchProvider(
        settings, settings.runtime.demo_data_path, build_daily_bar_provider(settings)
    )
    snapshot = research.dashboard()
    job_key = f"daily-scan:{snapshot.as_of.date().isoformat()}:{settings.scanning.universe_version}"
    existing = client.select("scan_runs", {"select": "*", "job_key": f"eq.{job_key}", "limit": "1"})
    if existing:
        return existing[0]
    coverage = snapshot.scan_coverage
    resolved = coverage.evaluated_count + coverage.excluded_count
    ratio = resolved / coverage.eligible_count
    if coverage.missing_symbols or ratio < settings.scanning.minimum_coverage_ratio:
        raise RuntimeError("Scan coverage gate failed; shortlist was not published")
    candidates = [c for c in snapshot.candidates if c.state in settings.scanning.archivable_states][
        : settings.universe.archive_limit
    ]
    owner = _owner_id()
    run_id = str(uuid4())
    client.insert(
        "scan_runs",
        {
            "id": run_id, "owner_id": owner, "job_key": job_key,
            "strategy_version": settings.strategy.version, "status": "COMPLETE",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "universe_size": coverage.eligible_count, "evaluated_count": coverage.evaluated_count,
            "ready_count": sum(c.state == "READY" for c in candidates),
            "watch_count": sum(c.state == "WATCH" for c in candidates),
            "metadata": {"source": snapshot.source, "coverage_ratio": ratio, "as_of": snapshot.as_of.isoformat()},
        },
    )
    for candidate in candidates:
        instrument = client.upsert(
            "instruments",
            {"symbol": candidate.symbol, "exchange": "NSE", "series": "EQ", "company_name": candidate.company, "sector": candidate.sector},
            on_conflict="exchange,symbol,series",
        )[0]
        alert = client.insert(
            "trade_alerts",
            {
                "owner_id": owner, "scan_run_id": run_id, "instrument_id": instrument["id"],
                "state": candidate.state, "score": candidate.score, "probability": candidate.probability,
                "entry_price": candidate.entry, "stop_loss": candidate.stop,
                "tp1": candidate.target_one, "tp2": candidate.target_two,
                "rationale": {"reasons": candidate.reasons, "contradictions": candidate.contradictions},
                "strategy_version": settings.strategy.version,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            },
        )[0]
        client.upsert(
            "notification_outbox",
            {
                "owner_id": owner, "channel": "TELEGRAM", "recipient": os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", ""),
                "template": "TRADE_ALERT", "payload": {"alert_id": alert["id"], "symbol": candidate.symbol,
                    "state": candidate.state, "entry": candidate.entry, "stop": candidate.stop,
                    "tp1": candidate.target_one, "tp2": candidate.target_two, "score": candidate.score},
                "dedupe_key": f"telegram:alert:{alert['id']}",
            },
            on_conflict="dedupe_key",
        )
    return client.select("scan_runs", {"select": "*", "id": f"eq.{run_id}"})[0]


def observe_paper_positions(client: SupabaseRest) -> dict[str, int]:
    positions = client.select("paper_positions", {"select": "*", "status": "eq.OPEN", "evidence": "eq.LIVE_PAPER"})
    processed = closed = 0
    for position in positions:
        candles = client.select(
            "market_candles",
            {"select": "*", "instrument_id": f"eq.{position['instrument_id']}", "timeframe": "eq.1d", "observation_kind": "eq.LIVE", "order": "observed_at.desc", "limit": "1"},
        )
        if not candles:
            continue
        candle = candles[0]
        dedupe = f"paper-observation:{position['id']}:{candle['id']}"
        if client.select("paper_execution_events", {"select": "id", "idempotency_key": f"eq.{dedupe}", "limit": "1"}):
            continue
        stop_hit = float(candle["low"]) <= float(position["stop_loss"])
        tp2_hit = float(candle["high"]) >= float(position["tp2"])
        metadata = position.get("metadata") or {}
        tp1_hit = not metadata.get("tp1_hit") and float(candle["high"]) >= float(position["tp1"])
        ambiguous = stop_hit and (tp1_hit or tp2_hit)
        event_type, price = ("STOP", position["stop_loss"]) if stop_hit else (("TP2", position["tp2"]) if tp2_hit else (("TP1", position["tp1"]) if tp1_hit else ("MARK", candle["close"])))
        client.insert("paper_execution_events", {
            "owner_id": position["owner_id"], "position_id": position["id"], "candle_id": candle["id"],
            "event_type": event_type, "event_at": candle["observed_at"], "price": price,
            "quantity": position["quantity"], "ambiguous": ambiguous, "idempotency_key": dedupe,
            "details": {"observation_kind": candle["observation_kind"], "conservative_stop_first": ambiguous},
        })
        processed += 1
        if event_type in {"STOP", "TP2"}:
            pnl = (float(price) - float(position["entry_price"])) * float(position["quantity"])
            client.update("paper_positions", {"status": "CLOSED", "closed_at": candle["observed_at"], "realized_pnl": pnl}, {"id": f"eq.{position['id']}"})
            closed += 1
        elif event_type == "TP1":
            client.update("paper_positions", {"metadata": {**metadata, "tp1_hit": True, "tp1_hit_at": candle["observed_at"]}}, {"id": f"eq.{position['id']}"})
    return {"processed": processed, "closed": closed}


def review_portfolio(client: SupabaseRest) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    positions = client.select("user_positions", {"select": "*", "status": "eq.OPEN", "opened_at": f"lte.{cutoff}"})
    created = 0
    for position in positions:
        latest = client.select("market_candles", {"select": "close,observed_at", "instrument_id": f"eq.{position['instrument_id']}", "timeframe": "eq.1d", "order": "observed_at.desc", "limit": "1"})
        if not latest:
            continue
        change = (float(latest[0]["close"]) / float(position["average_price"]) - 1) * 100
        verdict = "HOLD" if change >= 0 else "REVIEW"
        client.insert("position_reviews", {"owner_id": position["owner_id"], "position_id": position["id"], "verdict": verdict, "score": change, "reasons": [f"Seven-day mark-to-market return: {change:.2f}%"]})
        created += 1
    return {"reviewed": created}


def deliver_notifications(client: SupabaseRest) -> dict[str, int]:
    rows = client.select("notification_outbox", {"select": "*", "status": "in.(PENDING,FAILED)", "available_at": f"lte.{datetime.now(timezone.utc).isoformat()}", "order": "created_at.asc", "limit": "20"})
    sent = failed = 0
    bot = TelegramBot.from_environment()
    for row in rows:
        try:
            client.update("notification_outbox", {"status": "SENDING", "attempts": int(row["attempts"]) + 1}, {"id": f"eq.{row['id']}"})
            p = row["payload"]
            text = f"{p['state']} {p['symbol']}\nEntry ₹{p['entry']} | SL ₹{p['stop']}\nTP1 ₹{p['tp1']} | TP2 ₹{p['tp2']}\nScore {p['score']}/100\nPaper research only; no guaranteed return."
            result = bot.send(int(row["recipient"]), text)
            client.update("notification_outbox", {"status": "SENT", "sent_at": datetime.now(timezone.utc).isoformat(), "last_error": None}, {"id": f"eq.{row['id']}"})
            client.insert("notification_history", {"owner_id": row["owner_id"], "outbox_id": row["id"], "channel": "TELEGRAM", "provider_message_id": str(result.get("result", {}).get("message_id", "")), "status": "SENT", "response": {"ok": result.get("ok", False)}})
            sent += 1
        except Exception as error:
            client.update("notification_outbox", {"status": "FAILED", "last_error": str(error)[:500]}, {"id": f"eq.{row['id']}"})
            failed += 1
    return {"sent": sent, "failed": failed}


def retention_and_health(client: SupabaseRest) -> dict[str, Any]:
    history_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    client.delete("notification_history", {"created_at": f"lt.{history_cutoff}"})
    counts = {}
    for table in ("market_candles", "trade_alerts", "paper_execution_events", "notification_outbox"):
        counts[table] = client.count(table)
    status = "WARNING" if counts["market_candles"] > 1_500_000 else "HEALTHY"
    client.upsert("system_health", {
        "component": "supabase-retention", "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "details": {"row_counts": counts, "warning": "Review database size in Supabase dashboard" if status == "WARNING" else None},
    }, on_conflict="component")
    return {"status": status, "row_counts": counts}
