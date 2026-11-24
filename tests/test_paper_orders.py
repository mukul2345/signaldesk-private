import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from signaldesk.application import (
    DashboardService,
    DailyBriefService,
    PaperExecutionService,
    PerformanceValidationService,
    PaperOrderError,
    PaperOrderService,
    PositionExitService,
    ScanError,
    ScanService,
    ScanScheduler,
    SystemStatusService,
    StrategyResearchProvider,
)
from signaldesk.config import load_settings
from signaldesk.domain.models import DailyBar, PaperOrderRequest
from signaldesk.domain.strategy import DailyBreakoutStrategy, StrategyParameters
from signaldesk.infrastructure import (
    AngelOneCredentials,
    AngelOneDailyBarProvider,
    CorporateActionAdjuster,
    JsonExitReplayProvider,
    JsonReplayProvider,
    JsonResearchProvider,
    JsonTradingCalendar,
    NseCorporateActionClient,
    NseMcpDailyBarProvider,
    NseUniversePromotionService,
    NseUniverseError,
    NseUniverseSynchronizer,
    SqlitePaperOrderRepository,
    SqliteScanRepository,
    ScenarioDailyBarProvider,
    generate_totp,
    angel_one_credential_readiness,
)


class FakeAngelOneCandleClient:
    authenticated = True

    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    def candles(self, symbol_token, exchange, interval, start, end):
        self.requests.append((symbol_token, exchange, interval, start, end))
        return self.rows


class FakeNseMcpClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_stock_history":
            start = date(2026, 8, 1)
            return {
                "symbol": arguments["symbol"],
                "data": [
                    {
                        "date": (start + timedelta(days=index)).isoformat(),
                        "open": 100 + index,
                        "high": 102 + index,
                        "low": 99 + index,
                        "close": 101 + index,
                        "volume": 1000 + index,
                    }
                    for index in range(60)
                ],
            }
        if name == "get_bulk_quote":
            return {
                "quotes": [
                    {
                        "symbol": symbol,
                        "date": "2026-11-20",
                        "open": 160,
                        "high": 164,
                        "low": 159,
                        "close": 163,
                        "volume": 2200,
                    }
                    for symbol in arguments["symbols"]
                ]
            }
        if name == "get_market_mood":
            return {
                "date": "2026-11-20",
                "stock_breadth": {"up_pct": 70},
                "benchmarks": {
                    "Nifty 50": {"close": 26000, "change_pct": 1},
                    "Nifty 500": {"close": 24000, "change_pct": 0.8},
                    "NIFTY Midcap 100": {"close": 62000, "change_pct": 0.6},
                    "Nifty Next 50": {"close": 73000, "change_pct": -0.2},
                },
            }
        raise AssertionError(f"Unexpected NSE MCP tool {name}")


class FakeUniverseResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeUniverseHttpClient:
    def __init__(self, text):
        self.text = text

    def get(self, url):
        return FakeUniverseResponse(self.text)


class FakeCorporateActionResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeCorporateActionHttpClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, params):
        return FakeCorporateActionResponse(self.payload)


class PaperOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_config = Path("backend/config.default.json")
        raw = json.loads(source_config.read_text(encoding="utf-8"))
        raw["runtime"]["database_path"] = str(self.root / "test.db")
        raw["runtime"]["demo_data_path"] = str(
            Path("backend/data/dashboard.json").resolve()
        )
        raw["nse_mcp"]["universe_candidate_path"] = str(
            self.root / "nifty-500-candidate.json"
        )
        raw["nse_mcp"]["promoted_universe_path"] = str(
            self.root / "promoted-universe.json"
        )
        raw["nse_mcp"]["previous_universe_path"] = str(
            self.root / "previous-universe.json"
        )
        raw["corporate_actions"]["cache_path"] = str(
            self.root / "corporate-actions.json"
        )
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps(raw), encoding="utf-8")
        self.settings = load_settings(self.config)
        self.research = JsonResearchProvider(self.settings.runtime.demo_data_path)
        self.repository = SqlitePaperOrderRepository(
            self.settings.runtime.database_path
        )
        self.repository.initialize()
        self.scan_repository = SqliteScanRepository(
            self.settings.runtime.database_path
        )
        self.scan_repository.initialize()
        self.service = PaperOrderService(
            self.settings, self.research, self.repository
        )
        self.execution = PaperExecutionService(
            self.settings,
            JsonReplayProvider(self.settings.runtime.replay_data_path),
            self.repository,
        )
        self.position_exits = PositionExitService(
            self.settings,
            JsonExitReplayProvider(self.settings.runtime.exit_replay_data_path),
            self.repository,
        )
        self.scans = ScanService(
            self.settings, self.research, self.scan_repository
        )
        self.daily_brief = DailyBriefService(
            self.settings,
            self.research,
            self.repository,
            self.scans,
            self.scan_repository,
        )
        self.performance_validation = PerformanceValidationService(
            self.settings, self.repository
        )
        self.calendar = JsonTradingCalendar(self.settings.exchange_calendar.path)
        self.scheduler = ScanScheduler(
            self.settings, self.scans, self.scan_repository, self.calendar
        )
        self.system_status = SystemStatusService(
            self.settings,
            self.research,
            ScenarioDailyBarProvider(self.settings.runtime.strategy_fixture_path),
            self.repository,
            self.scan_repository,
            self.scheduler,
        )
        strategy = self.settings.strategy
        self.strategy = DailyBreakoutStrategy(
            StrategyParameters(
                version=strategy.version,
                warmup_bars=strategy.warmup_bars,
                fast_sma_period=strategy.fast_sma_period,
                slow_sma_period=strategy.slow_sma_period,
                breakout_lookback=strategy.breakout_lookback,
                volume_average_period=strategy.volume_average_period,
                minimum_volume_ratio=strategy.minimum_volume_ratio,
                atr_period=strategy.atr_period,
                initial_stop_atr_multiple=strategy.initial_stop_atr_multiple,
                entry_buffer_bps=strategy.entry_buffer_bps,
                maximum_entry_extension_bps=strategy.maximum_entry_extension_bps,
                target_one_r=strategy.target_one_r,
                target_two_r=strategy.target_two_r,
                maximum_holding_sessions=strategy.maximum_holding_sessions,
                tick_size=strategy.tick_size,
                watch_score_minimum=strategy.watch_score_minimum,
                ready_score_minimum=strategy.ready_score_minimum,
                trend_weight=strategy.score_weights.trend,
                breakout_weight=strategy.score_weights.breakout,
                volume_weight=strategy.score_weights.volume,
                market_weight=strategy.score_weights.market,
            )
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ready_candidate_creates_pending_order_with_risk_sizing(self) -> None:
        order = self.service.create(
            PaperOrderRequest(candidate_id="cdsl", idempotency_key="test-cdsl-order")
        )
        self.assertEqual(order.status, "PENDING_SIMULATION")
        self.assertEqual(order.quantity, 4)
        self.assertEqual(order.planned_risk, 204)
        self.assertEqual(order.required_cash, 6992)

    def test_idempotency_returns_existing_order(self) -> None:
        request = PaperOrderRequest(
            candidate_id="bel", idempotency_key="same-bel-order"
        )
        first = self.service.create(request)
        second = self.service.create(request)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.repository.list_orders()), 1)

    def test_watch_candidate_is_rejected(self) -> None:
        with self.assertRaises(PaperOrderError):
            self.service.create(
                PaperOrderRequest(
                    candidate_id="tatapower", idempotency_key="watch-order"
                )
            )

    def test_pending_order_reserves_cash_and_risk(self) -> None:
        self.service.create(
            PaperOrderRequest(candidate_id="cdsl", idempotency_key="reserve-cdsl")
        )
        dashboard = DashboardService(
            self.settings, self.research, self.repository
        ).view()
        self.assertEqual(dashboard.account.available_cash, 43008)
        self.assertEqual(dashboard.account.open_risk, 204)

    def test_duplicate_candidate_with_new_key_is_rejected(self) -> None:
        self.service.create(
            PaperOrderRequest(candidate_id="bel", idempotency_key="first-bel-key")
        )
        with self.assertRaises(PaperOrderError):
            self.service.create(
                PaperOrderRequest(candidate_id="bel", idempotency_key="second-bel-key")
            )

    def test_replay_waits_then_partially_and_fully_fills(self) -> None:
        order = self.service.create(
            PaperOrderRequest(candidate_id="cdsl", idempotency_key="replay-cdsl")
        )
        waiting = self.execution.advance(order.id)
        partial = self.execution.advance(order.id)
        filled = self.execution.advance(order.id)
        self.assertEqual(waiting.outcome, "WAITING_FOR_ENTRY")
        self.assertEqual(partial.outcome, "PARTIAL_FILL")
        self.assertEqual(partial.order.filled_quantity, 2)
        self.assertEqual(filled.outcome, "FILLED")
        self.assertEqual(filled.order.filled_quantity, 4)
        self.assertEqual(len(self.repository.list_fills()), 2)
        self.assertGreater(filled.order.average_fill_price, filled.order.entry_price)
        self.assertGreater(filled.order.fees, 0)

    def test_cancel_releases_unfilled_reservation(self) -> None:
        order = self.service.create(
            PaperOrderRequest(candidate_id="bel", idempotency_key="cancel-bel")
        )
        cancelled = self.execution.cancel(order.id)
        account = DashboardService(
            self.settings, self.research, self.repository
        ).paper_account()
        self.assertEqual(cancelled.status, "CANCELLED")
        self.assertEqual(account.reserved_cash, 0)
        self.assertEqual(account.available_cash, self.settings.capital_ceiling)

    def test_tp1_activates_trailing_then_trailing_stop_closes_position(self) -> None:
        order = self.service.create(
            PaperOrderRequest(candidate_id="cdsl", idempotency_key="exit-cdsl")
        )
        self.execution.advance(order.id)
        self.execution.advance(order.id)
        self.execution.advance(order.id)
        position = self.repository.list_positions()[0]

        hold = self.position_exits.advance(position.id)
        tp1 = self.position_exits.advance(position.id)
        trail = self.position_exits.advance(position.id)
        stopped = self.position_exits.advance(position.id)

        self.assertEqual(hold.outcome, "HOLD")
        self.assertEqual(tp1.outcome, "TP1_FILL")
        self.assertEqual(tp1.position.quantity_open, 2)
        self.assertTrue(tp1.position.trailing_active)
        self.assertEqual(tp1.position.current_stop, 1725)
        self.assertEqual(trail.outcome, "TRAILING_UPDATED")
        self.assertEqual(trail.position.current_stop, 1760)
        self.assertEqual(stopped.outcome, "TRAILING_STOP_FILL")
        self.assertEqual(stopped.position.status, "CLOSED")
        self.assertGreater(stopped.position.realized_pnl, 0)
        self.assertEqual(len(self.repository.list_exit_fills()), 2)

    def test_live_mode_is_rejected_by_configuration(self) -> None:
        raw = json.loads(Path("backend/config.default.json").read_text())
        raw["execution"]["live_enabled"] = True
        invalid = self.root / "invalid.json"
        invalid.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_settings(invalid)

    def test_complete_scan_archives_ranked_candidates_idempotently(self) -> None:
        first = self.scans.archive_current()
        second = self.scans.archive_current()
        history = self.scans.history()

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.status, "COMPLETE")
        self.assertEqual(first.coverage_ratio, 1)
        self.assertEqual([item.symbol for item in first.candidates], [
            "CDSL", "BEL", "TATAPOWER", "MAXHEALTH"
        ])
        self.assertEqual(len(history.runs), 1)

    def test_daily_mvp_brief_contains_ranked_trade_levels_and_portfolio(self) -> None:
        brief = self.daily_brief.run()

        self.assertIsNotNone(brief.scan)
        self.assertLessEqual(len(brief.top_setups), self.settings.universe.archive_limit)
        self.assertTrue(all(item.entry > item.stop for item in brief.top_setups))
        self.assertTrue(all(item.target_two > item.target_one for item in brief.top_setups))
        self.assertEqual(brief.portfolio.health, "NO_POSITIONS")
        self.assertEqual(brief.portfolio.open_positions, 0)
        self.assertIn("capital is not exposed", brief.portfolio.observations[0])

    def test_live_paper_validation_stays_blocked_without_sample(self) -> None:
        report = self.performance_validation.report()

        self.assertEqual(report.status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report.closed_trades, 0)
        self.assertEqual(
            report.minimum_required_trades,
            self.settings.evaluation.minimum_closed_trades,
        )
        self.assertFalse(report.target_observed)
        self.assertTrue(any("do not guarantee" in item for item in report.warnings))

    def test_incomplete_scan_cannot_be_archived(self) -> None:
        raw = json.loads(self.settings.runtime.demo_data_path.read_text())
        raw["scanCoverage"]["evaluatedCount"] = 4
        raw["scanCoverage"]["missingSymbols"] = ["PERSISTENT"]
        source = self.root / "incomplete-dashboard.json"
        source.write_text(json.dumps(raw), encoding="utf-8")
        incomplete = ScanService(
            self.settings,
            JsonResearchProvider(source),
            self.scan_repository,
        )

        with self.assertRaises(ScanError):
            incomplete.archive_current()

    def test_scheduler_claims_due_slot_once_and_persists_success(self) -> None:
        monday_1831_ist = datetime(2026, 11, 16, 13, 1, tzinfo=timezone.utc)

        first = self.scheduler.tick(monday_1831_ist)
        second = self.scheduler.tick(monday_1831_ist)
        status = self.scheduler.status(monday_1831_ist)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(status.jobs[0].status, "COMPLETE")
        self.assertEqual(status.jobs[0].attempts, 1)
        self.assertEqual(len(self.scans.history().runs), 1)

    def test_scheduler_skips_weekend_and_reports_next_weekday(self) -> None:
        sunday_noon_ist = datetime(2026, 11, 15, 6, 30, tzinfo=timezone.utc)

        self.assertEqual(self.scheduler.tick(sunday_noon_ist), [])
        next_run = self.scheduler.next_run(sunday_noon_ist)
        self.assertEqual(next_run.isoformat(), "2026-11-16T18:30:00+05:30")

    def test_scheduler_skips_official_exchange_holiday(self) -> None:
        monday_after_close_ist = datetime(2026, 11, 23, 13, 1, tzinfo=timezone.utc)

        next_run = self.scheduler.next_run(monday_after_close_ist)

        self.assertEqual(next_run.isoformat(), "2026-11-25T18:30:00+05:30")
        holiday_noon_ist = datetime(2026, 11, 24, 6, 30, tzinfo=timezone.utc)
        self.assertEqual(self.scheduler.tick(holiday_noon_ist), [])
        self.assertFalse(self.scheduler.status(holiday_noon_ist).current_day_is_session)

    def test_public_settings_are_hashed_and_do_not_expose_runtime_values(self) -> None:
        public = self.system_status.public_settings()
        payload = public.model_dump(mode="json", by_alias=True)
        encoded = json.dumps(payload)

        self.assertEqual(len(public.configuration_hash), 64)
        self.assertNotIn("runtime", payload)
        self.assertNotIn("database_path", encoded)
        self.assertNotIn("allowed_origins", encoded)
        self.assertFalse(public.execution.live_enabled)
        self.assertEqual(
            public.configuration_hash,
            self.system_status.public_settings().configuration_hash,
        )

    def test_system_health_reports_demo_and_fail_closed_providers(self) -> None:
        health = self.system_status.health()
        statuses = {component.id: component.status for component in health.components}

        self.assertEqual(health.overall, "SAFE_PAPER")
        self.assertTrue(health.paper_safety_enforced)
        self.assertEqual(statuses["database"], "HEALTHY")
        self.assertEqual(statuses["research"], "DEMO")
        self.assertEqual(statuses["market_data"], "DEMO")
        self.assertEqual(statuses["broker"], "NOT_CONFIGURED")

    @staticmethod
    def _trend_bars(final_close=127.5, final_high=128.0, final_open=127.0):
        start = date(2026, 8, 24)
        bars = []
        for index in range(55):
            close = 100 + index * 0.5
            bars.append(
                DailyBar(
                    session=start + timedelta(days=index),
                    open=close - 0.1,
                    high=close + 0.4,
                    low=close - 0.4,
                    close=close,
                    volume=1000,
                )
            )
        bars[-1] = DailyBar(
            session=bars[-1].session,
            open=final_open,
            high=final_high,
            low=min(final_open, final_close) - 0.4,
            close=final_close,
            volume=2000,
        )
        return bars

    def test_daily_strategy_produces_ready_plan_from_completed_bars(self) -> None:
        result = self.strategy.evaluate(self._trend_bars(), market_supportive=True)

        self.assertEqual(result.state, "READY")
        self.assertEqual(result.score, 100)
        self.assertGreater(result.entry, result.breakout_level)
        self.assertLess(result.stop, result.entry)
        self.assertGreater(result.target_two, result.target_one)
        self.assertEqual(result.maximum_holding_sessions, 15)

    def test_daily_strategy_watch_and_gap_avoid_are_distinct(self) -> None:
        watch = self.strategy.evaluate(
            self._trend_bars(final_close=126.8, final_high=126.85, final_open=126.7),
            market_supportive=True,
        )
        gap = self.strategy.evaluate(
            self._trend_bars(final_close=131, final_high=132, final_open=131),
            market_supportive=True,
        )

        self.assertEqual(watch.state, "WATCH")
        self.assertEqual(gap.state, "AVOID")
        self.assertIn("Price gapped or extended", " ".join(gap.contradictions))

    def test_daily_strategy_rejects_insufficient_history(self) -> None:
        result = self.strategy.evaluate(self._trend_bars()[:20], market_supportive=True)
        self.assertEqual(result.state, "INSUFFICIENT")
        self.assertIsNone(result.entry)

    def test_strategy_research_provider_builds_ranked_candidates_without_probability(self) -> None:
        provider = StrategyResearchProvider(
            self.settings,
            self.settings.runtime.demo_data_path,
            ScenarioDailyBarProvider(self.settings.runtime.strategy_fixture_path),
        )
        dashboard = provider.dashboard()

        self.assertEqual(dashboard.source, "illustrative_strategy_fixture")
        self.assertEqual([item.rank for item in dashboard.candidates], [1, 2, 3, 4, 5])
        self.assertEqual([item.state for item in dashboard.candidates], [
            "READY", "READY", "WATCH", "WATCH", "AVOID"
        ])
        self.assertTrue(all(item.probability is None for item in dashboard.candidates))
        self.assertEqual(dashboard.scan_coverage.evaluated_count, 5)

    def test_angel_one_provider_keeps_only_completed_daily_candles(self) -> None:
        manifest = self.root / "angel-instruments.json"
        manifest.write_text(json.dumps({"instruments": [{
            "symbol": "BEL",
            "company": "Bharat Electronics",
            "sector": "Defence",
            "symbol_token": "383",
        }]}), encoding="utf-8")
        self.settings.angel_one.instruments_path = manifest
        rows = [
            ["2026-11-20T00:00:00+05:30", 100, 105, 99, 104, 1000],
            ["2026-11-23T00:00:00+05:30", 104, 108, 103, 107, 1200],
        ]
        client = FakeAngelOneCandleClient(rows)
        credentials = AngelOneCredentials(
            api_key="key",
            client_code="client",
            pin="pin",
            totp_secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
            client_local_ip="127.0.0.1",
            client_public_ip="127.0.0.1",
            mac_address="00:00:00:00:00:00",
        )
        provider = AngelOneDailyBarProvider(
            self.settings.angel_one,
            credentials,
            client=client,
            now=lambda: datetime.fromisoformat("2026-11-23T12:00:00+05:30"),
        )

        instruments = provider.instruments()

        self.assertEqual([bar.session.isoformat() for bar in instruments[0].bars], ["2026-11-20"])
        self.assertEqual(client.requests[0][0:3], ("383", "NSE", "ONE_DAY"))
        self.assertEqual(provider.readiness().status, "HEALTHY")

    def test_nse_mcp_provider_warms_cache_then_uses_incremental_bulk_refresh(self) -> None:
        universe = self.root / "nse-universe.json"
        universe.write_text(json.dumps({"version": "test-one", "instruments": [{
            "symbol": "BEL",
            "company": "Bharat Electronics",
            "sector": "Defence",
        }]}), encoding="utf-8")
        self.settings.nse_mcp.universe_path = universe
        self.settings.nse_mcp.cache_path = self.root / "nse-cache.json"
        client = FakeNseMcpClient()
        provider = NseMcpDailyBarProvider(
            self.settings.nse_mcp,
            required_bars=self.settings.strategy.warmup_bars,
            client=client,
            now=lambda: datetime.fromisoformat("2026-11-22T12:00:00+05:30"),
        )

        first = provider.instruments()
        second = provider.instruments()

        self.assertEqual(first, second)
        self.assertEqual([call[0] for call in client.calls], [
            "get_stock_history", "get_bulk_quote", "get_market_mood"
        ])
        self.assertEqual(first[0].bars[-1].session.isoformat(), "2026-11-20")
        self.assertTrue(provider.market_supportive())
        self.assertEqual(len(provider.indices()), 4)
        self.assertEqual(provider.readiness().status, "HEALTHY")
        self.assertTrue(self.settings.nse_mcp.cache_path.exists())

    def test_nse_mcp_history_warmup_is_batched_and_resumable(self) -> None:
        active = self.root / "active-universe.json"
        active.write_text(json.dumps({
            "version": "active-one",
            "instruments": [{
                "symbol": "BEL", "company": "Bharat Electronics", "sector": "Defence"
            }],
        }), encoding="utf-8")
        candidate = self.settings.nse_mcp.universe_candidate_path
        candidate.write_text(json.dumps({
            "version": "candidate-three",
            "instruments": [
                {"symbol": "BEL", "company": "Bharat Electronics", "sector": "Defence"},
                {"symbol": "CDSL", "company": "Central Depository Services", "sector": "Financial Services"},
                {"symbol": "ABB", "company": "ABB India", "sector": "Capital Goods"},
            ],
        }), encoding="utf-8")
        self.settings.nse_mcp.universe_path = active
        self.settings.nse_mcp.cache_path = self.root / "warmup-cache.json"
        self.settings.nse_mcp.history_warmup_batch_size = 2
        client = FakeNseMcpClient()
        provider = NseMcpDailyBarProvider(
            self.settings.nse_mcp,
            required_bars=self.settings.strategy.warmup_bars,
            client=client,
            now=lambda: datetime.fromisoformat("2026-11-22T12:00:00+05:30"),
        )

        initial = provider.warmup_status()
        first = provider.warmup_next_batch()
        resumed_provider = NseMcpDailyBarProvider(
            self.settings.nse_mcp,
            required_bars=self.settings.strategy.warmup_bars,
            client=client,
            now=lambda: datetime.fromisoformat("2026-11-22T12:05:00+05:30"),
        )
        resumed = resumed_provider.warmup_next_batch()
        resumed_provider.instruments()

        self.assertEqual(initial.warmed_symbols, 0)
        self.assertEqual(first.warmed_symbols, 2)
        self.assertEqual(first.remaining_symbols, 1)
        self.assertEqual(resumed.warmed_symbols, 3)
        self.assertTrue(resumed.ready_to_activate)
        self.assertEqual(
            [name for name, _ in client.calls[:3]],
            ["get_stock_history", "get_stock_history", "get_stock_history"],
        )
        persisted = json.loads(self.settings.nse_mcp.cache_path.read_text())
        self.assertEqual(set(persisted["bars"]), {"ABB", "BEL", "CDSL"})

    def test_nse_universe_sync_validates_and_writes_separate_candidate(self) -> None:
        self.settings.nse_mcp.universe_expected_minimum = 2
        self.settings.nse_mcp.universe_expected_maximum = 3
        self.settings.nse_mcp.universe_candidate_path = self.root / "candidate.json"
        content = (
            "Company Name,Industry,Symbol,Series,ISIN Code\n"
            "Bharat Electronics Ltd.,Defence,BEL,EQ,INE263A01024\n"
            "Central Depository Services,Financial Services,CDSL,EQ,INE736A01011\n"
            "Ignored Preference,Other,IGNORE,BE,INE000000000\n"
        )
        synchronizer = NseUniverseSynchronizer(
            self.settings.nse_mcp,
            http_client=FakeUniverseHttpClient(content),
            now=lambda: datetime.fromisoformat("2026-11-22T12:00:00+00:00"),
        )

        payload = synchronizer.sync_candidate()

        self.assertEqual([item["symbol"] for item in payload["instruments"]], ["BEL", "CDSL"])
        self.assertTrue(self.settings.nse_mcp.universe_candidate_path.exists())
        self.assertEqual(
            json.loads(self.settings.nse_mcp.universe_candidate_path.read_text())["source"],
            self.settings.nse_mcp.universe_source_url,
        )

    def test_nse_universe_sync_rejects_unexpected_constituent_count(self) -> None:
        self.settings.nse_mcp.universe_expected_minimum = 2
        self.settings.nse_mcp.universe_expected_maximum = 3
        content = "Company Name,Industry,Symbol,Series\nOnly One,Other,ONE,EQ\n"

        with self.assertRaises(NseUniverseError):
            NseUniverseSynchronizer(
                self.settings.nse_mcp,
                http_client=FakeUniverseHttpClient(content),
            ).sync_candidate()

    def _promotion_service(self, corporate_rows):
        self.settings.nse_mcp.universe_expected_minimum = 2
        self.settings.nse_mcp.universe_expected_maximum = 3
        candidate = {
            "version": "candidate-two",
            "instruments": [
                {"symbol": "BEL", "company": "Bharat Electronics", "sector": "Defence"},
                {"symbol": "CDSL", "company": "Central Depository Services", "sector": "Financial Services"},
            ],
        }
        self.settings.nse_mcp.universe_candidate_path.write_text(
            json.dumps(candidate), encoding="utf-8"
        )
        bars = [item.model_dump(mode="json") for item in self._trend_bars()]
        self.settings.nse_mcp.cache_path = self.root / "promotion-bars.json"
        self.settings.nse_mcp.cache_path.write_text(json.dumps({
            "version": 1,
            "bars": {"BEL": bars, "CDSL": bars},
        }), encoding="utf-8")
        corporate_client = NseCorporateActionClient(
            self.settings.corporate_actions,
            http_client=FakeCorporateActionHttpClient(corporate_rows),
            now=lambda: datetime.fromisoformat("2026-11-23T12:00:00+00:00"),
        )
        return NseUniversePromotionService(
            self.settings,
            corporate_actions=corporate_client,
            now=lambda: datetime.fromisoformat("2026-11-23T12:05:00+00:00"),
        )

    def test_universe_promotion_is_blocked_by_price_affecting_action(self) -> None:
        service = self._promotion_service([{
            "symbol": "BEL",
            "series": "EQ",
            "subject": "Face Value Split (Sub-Division)",
            "exDate": "20-Nov-2026",
            "recDate": "20-Nov-2026",
        }])

        report = service.refresh_evidence()

        self.assertFalse(report.eligible_to_promote)
        self.assertEqual(report.blocking_action_count, 1)
        self.assertEqual(report.blocking_action_symbols, ["BEL"])

    def test_bonus_history_is_adjusted_without_mutating_raw_bars(self) -> None:
        adjuster = CorporateActionAdjuster(self.settings.corporate_actions)
        raw = [
            DailyBar(session=date(2026, 9, 30), open=100, high=104, low=98, close=102, volume=1000),
            DailyBar(session=date(2026, 10, 1), open=51, high=53, low=50, close=52, volume=2100),
        ]

        result = adjuster.adjust("BEL", raw, actions=[{
            "symbol": "BEL",
            "series": "EQ",
            "subject": "Bonus 1:1",
            "ex_date": "2026-10-01",
        }])

        self.assertEqual(len(result.applied), 1)
        self.assertEqual(result.unresolved_subjects, [])
        self.assertEqual(result.bars[0].close, 51)
        self.assertEqual(result.bars[0].volume, 2000)
        self.assertEqual(raw[0].close, 102)

    def test_rights_issue_requires_authoritative_adjusted_prices(self) -> None:
        adjuster = CorporateActionAdjuster(self.settings.corporate_actions)
        result = adjuster.adjust("BEL", self._trend_bars(), actions=[{
            "symbol": "BEL",
            "series": "EQ",
            "subject": "Rights 2:21 @ Premium Rs 748/-",
            "ex_date": "2026-10-01",
        }])

        self.assertEqual(result.applied, [])
        self.assertEqual(
            result.unresolved_subjects,
            ["Rights 2:21 @ Premium Rs 748/-"],
        )

    def test_guarded_universe_promotion_writes_backup_and_requires_restart(self) -> None:
        service = self._promotion_service([{
            "symbol": "BEL",
            "series": "EQ",
            "subject": "Interim Dividend - Re 1 Per Share",
            "exDate": "20-Nov-2026",
            "recDate": "20-Nov-2026",
        }])

        report = service.refresh_evidence()
        promoted = service.promote("candidate-two")

        self.assertTrue(report.eligible_to_promote)
        self.assertEqual(promoted.prepared_version, "candidate-two")
        self.assertTrue(promoted.restart_required)
        self.assertTrue(self.settings.nse_mcp.promoted_universe_path.exists())
        self.assertTrue(self.settings.nse_mcp.previous_universe_path.exists())
        payload = json.loads(self.settings.nse_mcp.promoted_universe_path.read_text())
        self.assertEqual(payload["promotion_evidence"]["blocking_action_count"], 0)
        reloaded = load_settings(self.config)
        self.assertEqual(reloaded.scanning.universe_version, "candidate-two")

    def test_angel_one_credentials_report_only_missing_field_names(self) -> None:
        credentials = AngelOneCredentials.from_environment({"ANGEL_API_KEY": "secret"})
        missing = credentials.missing_environment_fields()

        self.assertNotIn("secret", " ".join(missing))
        self.assertEqual(missing, [
            "ANGEL_CLIENT_CODE",
            "ANGEL_PIN",
            "ANGEL_TOTP_SECRET",
            "ANGEL_CLIENT_PUBLIC_IP",
            "ANGEL_MAC_ADDRESS",
        ])

    def test_totp_matches_rfc_vector_without_external_dependency(self) -> None:
        self.assertEqual(
            generate_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", at=59),
            "287082",
        )

    def test_angel_one_readiness_rejects_temporary_totp_code(self) -> None:
        credentials = AngelOneCredentials(
            api_key="key",
            client_code="client",
            pin="pin",
            totp_secret="123456",
            client_local_ip="127.0.0.1",
            client_public_ip="203.0.113.1",
            mac_address="00:11:22:33:44:55",
        )
        readiness = angel_one_credential_readiness(
            credentials,
            ScenarioDailyBarProvider(self.settings.runtime.strategy_fixture_path),
        )

        self.assertEqual(readiness.status, "ERROR")
        self.assertIn("Base32 setup secret", readiness.detail)

    def test_default_configuration_resolves_project_paths(self) -> None:
        settings = load_settings()
        self.assertTrue(settings.runtime.demo_data_path.exists())
        self.assertTrue(settings.nse_mcp.universe_path.exists())
        self.assertEqual(settings.providers.market_data, "nse_mcp")
        self.assertEqual(settings.mode, "paper")

    def test_production_environment_redirects_mutable_state(self) -> None:
        state = self.root / "persistent-state"
        with patch.dict(
            "os.environ",
            {
                "SIGNALDESK_ENVIRONMENT": "production",
                "SIGNALDESK_STATE_DIR": str(state),
                "SIGNALDESK_SERVE_FRONTEND": "true",
                "SIGNALDESK_REQUIRE_BASIC_AUTH": "true",
                "SIGNALDESK_AUTO_WARMUP": "true",
                "SIGNALDESK_BOOTSTRAP_UNIVERSE": "true",
                "SIGNALDESK_PUBLIC_ORIGIN": "https://signaldesk.example",
                "PORT": "9000",
            },
            clear=False,
        ):
            deployed = load_settings(self.config)

        self.assertEqual(deployed.deployment.environment, "production")
        self.assertTrue(deployed.deployment.serve_frontend)
        self.assertTrue(deployed.deployment.require_basic_auth)
        self.assertTrue(deployed.nse_mcp.automatic_history_warmup_enabled)
        self.assertTrue(deployed.nse_mcp.bootstrap_candidate_on_startup)
        self.assertEqual(
            deployed.runtime.database_path, state.resolve() / "signaldesk.db"
        )
        self.assertEqual(
            deployed.nse_mcp.cache_path, state.resolve() / "nse-mcp-cache.json"
        )
        self.assertEqual(deployed.runtime.allowed_origins, ["https://signaldesk.example"])
        self.assertEqual(deployed.runtime.api_port, 9000)


if __name__ == "__main__":
    unittest.main()
