from pathlib import Path

from fastapi.testclient import TestClient

from signaldesk.api.cloud_app import create_cloud_app
from signaldesk.application.cloud_jobs import observe_paper_positions


ROOT = Path(__file__).parents[1]


def test_migration_has_required_tables_and_rls():
    sql = (ROOT / "supabase/migrations/202611240001_cloud_foundation.sql").read_text()
    required = {
        "instruments", "market_candles", "trade_alerts", "paper_positions",
        "paper_execution_events", "user_positions", "user_transactions",
        "position_reviews", "portfolio_snapshots", "strategy_performance",
        "scan_runs", "scan_checkpoints", "scheduled_jobs", "market_data_checkpoints",
        "telegram_users", "notification_outbox", "notification_history", "risk_settings", "system_health",
    }
    for table in required:
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql


def test_auth_migration_creates_risk_profile_for_new_user():
    sql = (ROOT / "supabase/migrations/202611240003_auth_user_profile.sql").read_text()
    assert "after insert on auth.users" in sql
    assert "insert into public.risk_settings" in sql


def test_telegram_webhook_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    response = TestClient(create_cloud_app()).post("/api/telegram/webhook", json={})
    assert response.status_code == 401


def test_cloud_health_never_exposes_credentials(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable-test")
    payload = TestClient(create_cloud_app()).get("/api/health").json()
    assert payload == {"status": "ok", "runtime": "serverless", "paper_only": True}
    assert "publishable-test" not in str(payload)


def test_forward_paper_uses_live_candle_and_stops_first_when_ambiguous():
    class FakeClient:
        def __init__(self):
            self.inserted = []
            self.updated = []

        def select(self, table, params):
            if table == "paper_positions":
                return [{"id": "p1", "owner_id": "u1", "instrument_id": "i1", "quantity": 2,
                    "entry_price": 100, "stop_loss": 95, "tp1": 105, "tp2": 110, "metadata": {}}]
            if table == "market_candles":
                assert params["observation_kind"] == "eq.LIVE"
                return [{"id": "c1", "observed_at": "2026-11-24T10:00:00Z", "low": 94,
                    "high": 111, "close": 103, "observation_kind": "LIVE"}]
            if table == "paper_execution_events":
                return []
            raise AssertionError(table)

        def insert(self, table, values):
            self.inserted.append((table, values)); return [values]

        def update(self, table, values, params):
            self.updated.append((table, values, params)); return [values]

    client = FakeClient()
    result = observe_paper_positions(client)  # type: ignore[arg-type]
    assert result == {"processed": 1, "closed": 1}
    assert client.inserted[0][1]["event_type"] == "STOP"
    assert client.inserted[0][1]["ambiguous"] is True
    assert client.updated[0][1]["realized_pnl"] == -10
