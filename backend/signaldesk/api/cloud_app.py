"""Stateless cloud API. It never starts schedulers or writes local files."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from signaldesk.infrastructure.supabase_rest import CloudConfigurationError, SupabaseRest
from signaldesk.infrastructure.telegram import TelegramBot


def create_cloud_app() -> FastAPI:
    app = FastAPI(title="SignalDesk Cloud API", version="0.2.0")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        configured = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_PUBLISHABLE_KEY"))
        return {"status": "ok" if configured else "configuration_required", "runtime": "serverless", "paper_only": True}

    @app.get("/api/cloud/alerts")
    def alerts(authorization: str = Header(default="")) -> list[dict[str, Any]]:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Supabase access token required")
        try:
            return SupabaseRest.user(authorization[7:]).select(
                "trade_alerts",
                {"select": "*,instruments(symbol,company_name,sector)", "order": "score.desc", "limit": "5"},
            )
        except CloudConfigurationError as error:
            raise HTTPException(503, str(error)) from error

    def user_client(authorization: str) -> tuple[SupabaseRest, dict[str, Any]]:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Supabase access token required")
        client = SupabaseRest.user(authorization[7:])
        try:
            return client, client.auth_user()
        except Exception as error:
            raise HTTPException(401, "Invalid or expired Supabase session") from error

    @app.get("/api/cloud/dashboard")
    def cloud_dashboard(authorization: str = Header(default="")) -> dict[str, Any]:
        client, user = user_client(authorization)
        alerts = client.select("trade_alerts", {
            "select": "*,instruments(symbol,company_name,sector)", "status": "eq.ACTIVE",
            "order": "score.desc", "limit": "5",
        })
        risk = client.select("risk_settings", {"select": "*", "owner_id": f"eq.{user['id']}", "limit": "1"})
        positions = client.select("paper_positions", {"select": "*", "status": "eq.OPEN"})
        capital = float(risk[0]["capital"] if risk else os.environ.get("PAPER_CAPITAL_INR", "50000"))
        deployed = sum(float(p["entry_price"]) * float(p["quantity"]) for p in positions)
        open_risk = sum(max(float(p["entry_price"]) - float(p["stop_loss"]), 0) * float(p["quantity"]) for p in positions)
        candidates = []
        for rank, alert in enumerate(alerts, 1):
            instrument = alert.get("instruments") or {}
            rationale = alert.get("rationale") or {}
            candidates.append({
                "id": alert["id"], "rank": rank, "symbol": instrument.get("symbol", "?"),
                "company": instrument.get("company_name") or instrument.get("symbol", "?"),
                "sector": instrument.get("sector") or "Unclassified", "price": float(alert["entry_price"]),
                "changePercent": 0, "score": int(float(alert["score"])), "state": alert["state"],
                "setup": "Daily range breakout", "volumeRatio": 0, "entry": float(alert["entry_price"]),
                "stop": float(alert["stop_loss"]), "targetOne": float(alert["tp1"]), "targetTwo": float(alert["tp2"]),
                "probability": int(float(alert["probability"])) if alert.get("probability") is not None else None,
                "reasons": rationale.get("reasons", []), "contradictions": rationale.get("contradictions", []),
            })
        as_of = alerts[0]["created_at"] if alerts else datetime.now(timezone.utc).isoformat()
        return {
            "as_of": as_of, "source": "supabase_cloud", "market_status": "PAPER RESEARCH",
            "next_scan": "Weekdays · 18:30 IST", "indices": [], "candidates": candidates,
            "account": {"availableCash": max(capital-deployed, 0), "deployed": deployed, "openRisk": open_risk, "todayPnl": 0},
            "policy": {"capitalCeiling": capital, "riskPerTrade": capital * float(risk[0]["risk_per_trade_pct"] if risk else 1) / 100, "displayLimit": 5},
            "pendingOrders": [],
            "scanCoverage": {"eligibleCount": max(len(candidates), 1), "evaluatedCount": len(candidates), "excludedCount": 0, "missingSymbols": []},
        }

    @app.post("/api/cloud/paper/orders")
    def create_cloud_paper_order(body: dict[str, Any], authorization: str = Header(default="")) -> dict[str, Any]:
        client, user = user_client(authorization)
        alert_id = str(body.get("candidate_id", ""))
        idempotency_key = str(body.get("idempotency_key", ""))
        if len(idempotency_key) < 8:
            raise HTTPException(422, "Idempotency key is required")
        existing = client.select("paper_positions", {"select": "*", "entry_idempotency_key": f"eq.{idempotency_key}", "limit": "1"})
        if existing:
            return existing[0]
        alerts = client.select("trade_alerts", {"select": "*", "id": f"eq.{alert_id}", "status": "eq.ACTIVE", "limit": "1"})
        if not alerts:
            raise HTTPException(404, "Active alert not found")
        alert = alerts[0]
        risk_rows = client.select("risk_settings", {"select": "*", "owner_id": f"eq.{user['id']}", "limit": "1"})
        capital = float(risk_rows[0]["capital"] if risk_rows else 50000)
        risk_pct = float(risk_rows[0]["risk_per_trade_pct"] if risk_rows else 1)
        unit_risk = float(alert["entry_price"]) - float(alert["stop_loss"])
        if unit_risk <= 0:
            raise HTTPException(409, "Invalid alert risk geometry")
        quantity = max(int((capital * risk_pct / 100) // unit_risk), 1)
        created = client.insert("paper_positions", {
            "owner_id": user["id"], "alert_id": alert["id"], "instrument_id": alert["instrument_id"],
            "evidence": "LIVE_PAPER", "quantity": quantity, "entry_price": alert["entry_price"],
            "stop_loss": alert["stop_loss"], "tp1": alert["tp1"], "tp2": alert["tp2"],
            "entry_idempotency_key": idempotency_key,
        })[0]
        return {**created, "symbol": "", "candidate_id": alert_id, "planned_risk": quantity*unit_risk,
            "required_cash": quantity*float(alert["entry_price"]), "stop_price": alert["stop_loss"],
            "target_one": alert["tp1"], "target_two": alert["tp2"], "filled_quantity": quantity,
            "average_fill_price": alert["entry_price"], "fees": 0, "updated_at": created["opened_at"]}

    @app.get("/api/cloud/paper/account")
    def cloud_paper_account(authorization: str = Header(default="")) -> dict[str, Any]:
        client, user = user_client(authorization)
        rows = client.select("paper_positions", {"select": "*,instruments(symbol)", "order": "opened_at.desc"})
        risk = client.select("risk_settings", {"select": "*", "owner_id": f"eq.{user['id']}", "limit": "1"})
        capital = float(risk[0]["capital"] if risk else 50000)
        positions, orders = [], []
        for row in rows:
            symbol = (row.get("instruments") or {}).get("symbol", "?")
            quantity = int(float(row["quantity"]))
            orders.append({"id": row["id"], "candidate_id": row.get("alert_id") or row["id"], "symbol": symbol,
                "status": "FILLED", "quantity": quantity, "entry_price": float(row["entry_price"]),
                "stop_price": float(row["stop_loss"]), "target_one": float(row["tp1"]), "target_two": float(row["tp2"]),
                "planned_risk": max(float(row["entry_price"])-float(row["stop_loss"]),0)*quantity,
                "required_cash": float(row["entry_price"])*quantity, "idempotency_key": row["entry_idempotency_key"],
                "created_at": row["opened_at"], "filled_quantity": quantity, "average_fill_price": float(row["entry_price"]),
                "fees": 0, "updated_at": row.get("closed_at") or row["opened_at"]})
            positions.append({"id": row["id"], "order_id": row["id"], "symbol": symbol, "status": row["status"],
                "quantity_open": quantity if row["status"] == "OPEN" else 0,
                "quantity_closed": quantity if row["status"] == "CLOSED" else 0,
                "average_entry_price": float(row["entry_price"]), "current_stop": float(row["stop_loss"]),
                "target_one": float(row["tp1"]), "target_two": float(row["tp2"]), "tp1_quantity": 0,
                "tp1_filled_quantity": 0, "trailing_active": bool((row.get("metadata") or {}).get("tp1_hit")),
                "highest_price": float(row["entry_price"]), "entry_fees": 0, "exit_fees": 0,
                "realized_pnl": float(row["realized_pnl"]), "updated_at": row.get("closed_at") or row["opened_at"]})
        open_rows = [row for row in rows if row["status"] == "OPEN"]
        deployed = sum(float(r["entry_price"])*float(r["quantity"]) for r in open_rows)
        reserved = sum(max(float(r["entry_price"])-float(r["stop_loss"]),0)*float(r["quantity"]) for r in open_rows)
        return {"orders": orders, "fills": [], "positions": positions, "exitFills": [],
            "availableCash": max(capital-deployed,0), "reservedCash": 0, "deployedValue": deployed, "reservedRisk": reserved}

    @app.get("/api/cloud/portfolio/analysis")
    def cloud_portfolio_analysis(authorization: str = Header(default="")) -> dict[str, Any]:
        account = cloud_paper_account(authorization)
        positions = []
        for p in account["positions"]:
            value = p["average_entry_price"] * p["quantity_open"]
            positions.append({"symbol": p["symbol"], "status": p["status"], "quantity": p["quantity_open"],
                "averageEntry": p["average_entry_price"], "currentPrice": p["average_entry_price"],
                "currentStop": p["current_stop"], "targetOne": p["target_one"], "targetTwo": p["target_two"],
                "marketValue": value, "unrealizedPnl": 0, "realizedPnl": p["realized_pnl"],
                "distanceToStopPercent": (p["average_entry_price"]-p["current_stop"])/p["average_entry_price"]*100,
                "nextTarget": p["target_two"] if p["trailing_active"] else p["target_one"]})
        open_positions = [p for p in positions if p["status"] == "OPEN"]
        market_value = sum(p["marketValue"] for p in open_positions)
        concentration = max((p["marketValue"] for p in open_positions), default=0)/market_value*100 if market_value else 0
        return {"as_of": datetime.now(timezone.utc).isoformat(), "health": "HEALTHY" if open_positions else "NO_POSITIONS",
            "openPositions": len(open_positions), "costBasis": market_value, "marketValue": market_value,
            "unrealizedPnl": 0, "realizedPnl": sum(p["realizedPnl"] for p in positions),
            "reservedRisk": account["reservedRisk"], "largestPositionPercent": concentration,
            "staleSymbols": [], "observations": ["Cloud portfolio uses the latest persisted forward-paper evidence."], "positions": positions}

    @app.get("/api/cloud/mvp/daily-brief")
    def cloud_daily_brief(authorization: str = Header(default="")) -> dict[str, Any]:
        dashboard = cloud_dashboard(authorization)
        portfolio = cloud_portfolio_analysis(authorization)
        return {"generatedAt": datetime.now(timezone.utc).isoformat(), "scan": None,
            "topSetups": dashboard["candidates"], "portfolio": portfolio,
            "message": f"{len(dashboard['candidates'])} setup(s) in the latest cloud shortlist."}

    @app.get("/api/cloud/validation/performance")
    def cloud_performance(authorization: str = Header(default="")) -> dict[str, Any]:
        client, _ = user_client(authorization)
        closed = client.select("paper_positions", {"select": "realized_pnl,closed_at", "status": "eq.CLOSED", "evidence": "eq.LIVE_PAPER"})
        wins = sum(float(row["realized_pnl"]) > 0 for row in closed)
        pnl = sum(float(row["realized_pnl"]) for row in closed)
        count = len(closed)
        return {"status": "EVIDENCE_READY" if count >= 30 else "INSUFFICIENT_EVIDENCE", "closedTrades": count,
            "minimumRequiredTrades": 30, "winningTrades": wins, "losingTrades": count-wins,
            "winRatePercent": wins/count*100 if count else 0, "netPnl": pnl,
            "averagePnlPerTrade": pnl/count if count else 0, "maximumDrawdown": 0, "maximumDrawdownPercent": 0,
            "last30DayReturnPercent": pnl/50000*100, "targetMonthlyReturnPercent": 30,
            "targetObserved": pnl/50000*100 >= 30, "months": [],
            "warnings": ["Only genuine LIVE_PAPER closures are included.", "Thirty percent monthly return is aspirational and not guaranteed."]}

    @app.post("/api/cloud/portfolio/transactions")
    def cloud_portfolio_transaction(body: dict[str, Any], authorization: str = Header(default="")) -> dict[str, Any]:
        client, _ = user_client(authorization)
        required = ("instrument_id", "side", "quantity", "price", "idempotency_key")
        if any(body.get(key) in (None, "") for key in required):
            raise HTTPException(422, "instrument_id, side, quantity, price and idempotency_key are required")
        return client.request("POST", "rpc/record_portfolio_transaction", json={
            "p_instrument_id": body["instrument_id"], "p_side": str(body["side"]).upper(),
            "p_quantity": body["quantity"], "p_price": body["price"], "p_fees": body.get("fees", 0),
            "p_transacted_at": body.get("transacted_at") or datetime.now(timezone.utc).isoformat(),
            "p_idempotency_key": body["idempotency_key"], "p_notes": body.get("notes"),
        })

    @app.post("/api/telegram/webhook")
    def telegram_webhook(
        request: Request,
        update: dict[str, Any],
        x_telegram_bot_api_secret_token: str = Header(default=""),
    ) -> dict[str, bool]:
        expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        if not expected or not secrets.compare_digest(x_telegram_bot_api_secret_token, expected):
            raise HTTPException(401, "Invalid Telegram webhook secret")
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        command = str(message.get("text", "")).split()[0].lower()
        allowed = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "")
        if not chat_id or (allowed and str(chat_id) != allowed):
            return {"ok": True}
        if command in {"/start", "/help"}:
            TelegramBot.from_environment().send(
                int(chat_id),
                "SignalDesk paper-research bot. Commands: /health, /alerts. No profit is guaranteed.",
            )
        elif command == "/health":
            TelegramBot.from_environment().send(int(chat_id), "SignalDesk cloud API is online (paper mode).")
        elif command == "/alerts":
            TelegramBot.from_environment().send(int(chat_id), "Open the authenticated dashboard for the latest top-five alerts.")
        return {"ok": True}

    return app


app = create_cloud_app()
