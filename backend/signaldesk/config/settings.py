from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from dotenv import load_dotenv


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskSettings(StrictModel):
    risk_per_trade: int = Field(gt=0)
    maximum_aggregate_initial_risk: int = Field(gt=0)
    maximum_position_value: int = Field(gt=0)
    maximum_open_positions: int = Field(gt=0)


class ProviderSettings(StrictModel):
    research: str = Field(min_length=1)
    market_data: str = Field(min_length=1)
    execution: str = Field(min_length=1)
    institutional_data: str = Field(min_length=1)


class UniverseSettings(StrictModel):
    display_limit: int = Field(gt=0)
    archive_limit: int = Field(gt=0)


class ScanningSettings(StrictModel):
    universe_version: str = Field(min_length=1)
    snapshot_label: str = Field(min_length=1)
    schedule_slots: List[str] = Field(min_length=1)
    timezone: str = Field(min_length=1)
    automatic_enabled: bool
    active_weekdays: List[int] = Field(min_length=1)
    poll_interval_seconds: int = Field(gt=0)
    catch_up_window_minutes: int = Field(gt=0)
    job_lease_seconds: int = Field(gt=0)
    maximum_attempts: int = Field(gt=0)
    job_history_limit: int = Field(gt=0)
    history_retention_days: int = Field(gt=0)
    minimum_coverage_ratio: float = Field(gt=0, le=1)
    archivable_states: List[Literal["READY", "WATCH"]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schedule(self) -> "ScanningSettings":
        if any(day < 0 or day > 6 for day in self.active_weekdays):
            raise ValueError("Active weekdays must use Monday=0 through Sunday=6")
        for slot in self.schedule_slots:
            try:
                hour, minute = (int(part) for part in slot.split(":"))
            except (TypeError, ValueError):
                raise ValueError("Schedule slots must use HH:MM")
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Schedule slots must use valid 24-hour time")
        return self


class StrategyScoreWeights(StrictModel):
    trend: int = Field(ge=0)
    breakout: int = Field(ge=0)
    volume: int = Field(ge=0)
    market: int = Field(ge=0)


class StrategySettings(StrictModel):
    version: str = Field(min_length=1)
    warmup_bars: int = Field(gt=0)
    fast_sma_period: int = Field(gt=0)
    slow_sma_period: int = Field(gt=0)
    breakout_lookback: int = Field(gt=0)
    volume_average_period: int = Field(gt=0)
    minimum_volume_ratio: float = Field(gt=0)
    atr_period: int = Field(gt=0)
    initial_stop_atr_multiple: float = Field(gt=0)
    entry_buffer_bps: int = Field(ge=0)
    maximum_entry_extension_bps: int = Field(ge=0)
    target_one_r: float = Field(gt=0)
    target_two_r: float = Field(gt=0)
    maximum_holding_sessions: int = Field(gt=0)
    tick_size: float = Field(gt=0)
    watch_score_minimum: int = Field(ge=0, le=100)
    ready_score_minimum: int = Field(ge=0, le=100)
    score_weights: StrategyScoreWeights

    @model_validator(mode="after")
    def validate_contract(self) -> "StrategySettings":
        required = max(
            self.slow_sma_period,
            self.breakout_lookback + 1,
            self.volume_average_period + 1,
            self.atr_period + 1,
        )
        if self.warmup_bars < required:
            raise ValueError("Strategy warmup is shorter than an indicator requirement")
        if self.fast_sma_period >= self.slow_sma_period:
            raise ValueError("Fast SMA period must be shorter than slow SMA period")
        if self.target_two_r <= self.target_one_r:
            raise ValueError("Target two must exceed target one")
        if self.ready_score_minimum <= self.watch_score_minimum:
            raise ValueError("READY score must exceed WATCH score")
        if sum(self.score_weights.model_dump().values()) != 100:
            raise ValueError("Strategy score weights must total 100")
        return self


class AngelOneSettings(StrictModel):
    base_url: str = Field(min_length=1)
    instruments_path: Path
    exchange: str = Field(min_length=1)
    interval: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    cutoff_time: str = Field(min_length=1)
    lookback_calendar_days: int = Field(gt=0)
    cache_ttl_seconds: int = Field(ge=0)
    request_timeout_seconds: float = Field(gt=0)
    market_supportive: bool


class NseMcpSettings(StrictModel):
    bhavcopy_url: str = Field(min_length=1)
    universe_path: Path
    universe_candidate_path: Path
    promoted_universe_path: Path
    previous_universe_path: Path
    universe_source_url: str = Field(min_length=1)
    universe_expected_minimum: int = Field(gt=0)
    universe_expected_maximum: int = Field(gt=0)
    history_warmup_batch_size: int = Field(gt=0, le=25)
    bootstrap_candidate_on_startup: bool
    automatic_history_warmup_enabled: bool
    history_warmup_interval_seconds: int = Field(gt=0)
    cache_path: Path
    timezone: str = Field(min_length=1)
    cutoff_time: str = Field(min_length=1)
    history_months: int = Field(gt=0, le=3)
    cache_ttl_seconds: int = Field(ge=0)
    request_timeout_seconds: float = Field(gt=0)
    bulk_batch_size: int = Field(gt=0, le=50)
    index_names: List[str] = Field(min_length=1)
    market_supportive_min_stock_up_percent: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_universe_bounds(self) -> "NseMcpSettings":
        if self.universe_expected_maximum < self.universe_expected_minimum:
            raise ValueError("NSE universe maximum must be at least its minimum")
        return self


class ExchangeCalendarSettings(StrictModel):
    path: Path


class CorporateActionSettings(StrictModel):
    url: str = Field(min_length=1)
    cache_path: Path
    lookback_days: int = Field(gt=0)
    cache_ttl_seconds: int = Field(gt=0)
    request_timeout_seconds: float = Field(gt=0)
    blocking_keywords: List[str] = Field(min_length=1)
    bonus_ratio_pattern: str = Field(min_length=1)
    face_value_ratio_pattern: str = Field(min_length=1)
    adjustment_price_decimals: int = Field(ge=0, le=8)
    adjustment_volume_decimals: int = Field(ge=0, le=8)
    maximum_unexplained_gap_percent: float = Field(gt=0, le=100)
    report_symbol_limit: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_adjustment_patterns(self) -> "CorporateActionSettings":
        for pattern in (self.bonus_ratio_pattern, self.face_value_ratio_pattern):
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as error:
                raise ValueError("Corporate-action adjustment pattern is invalid") from error
            if compiled.groups != 2:
                raise ValueError(
                    "Corporate-action adjustment patterns require two capture groups"
                )
        return self


class RuntimeSettings(StrictModel):
    database_path: Path
    demo_data_path: Path
    strategy_fixture_path: Path
    replay_data_path: Path
    exit_replay_data_path: Path
    allowed_origins: List[str]
    api_host: str
    api_port: int = Field(gt=0, le=65535)


class DeploymentSettings(StrictModel):
    environment: Literal["local", "production"]
    serve_frontend: bool
    require_basic_auth: bool


class ExecutionSettings(StrictModel):
    paper_enabled: bool
    live_enabled: bool
    require_individual_entry_approval: bool


class PaperExecutionSettings(StrictModel):
    slippage_bps: int = Field(ge=0, le=1000)
    fee_bps: int = Field(ge=0, le=1000)
    tp1_fraction: float = Field(gt=0, lt=1)


class EvaluationSettings(StrictModel):
    minimum_closed_trades: int = Field(gt=0)
    maximum_acceptable_drawdown_percent: float = Field(gt=0, le=100)
    target_monthly_return_percent: float = Field(gt=0)


class AppSettings(StrictModel):
    schema_version: str
    mode: str
    currency: str
    capital_ceiling: int = Field(gt=0)
    providers: ProviderSettings
    risk: RiskSettings
    universe: UniverseSettings
    strategy: StrategySettings
    angel_one: AngelOneSettings
    nse_mcp: NseMcpSettings
    exchange_calendar: ExchangeCalendarSettings
    corporate_actions: CorporateActionSettings
    scanning: ScanningSettings
    runtime: RuntimeSettings
    deployment: DeploymentSettings
    execution: ExecutionSettings
    paper_execution: PaperExecutionSettings
    evaluation: EvaluationSettings

    @model_validator(mode="after")
    def enforce_paper_safety(self) -> "AppSettings":
        if self.mode != "paper":
            raise ValueError("Only paper mode is implemented")
        if self.execution.live_enabled:
            raise ValueError("Live execution must remain disabled")
        if self.risk.maximum_position_value > self.capital_ceiling:
            raise ValueError("Maximum position value exceeds capital ceiling")
        return self


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_settings(config_path: Optional[Path] = None) -> AppSettings:
    root = _project_root()
    load_dotenv(root / ".env", override=False)
    configured = os.environ.get("SIGNALDESK_CONFIG_PATH")
    selected = config_path or Path(configured or root / "backend/config.default.json")
    if not selected.is_absolute():
        selected = root / selected
    raw = json.loads(selected.read_text(encoding="utf-8"))
    if os.environ.get("SIGNALDESK_ENVIRONMENT"):
        raw["deployment"]["environment"] = os.environ["SIGNALDESK_ENVIRONMENT"]
    if os.environ.get("SIGNALDESK_SERVE_FRONTEND"):
        raw["deployment"]["serve_frontend"] = os.environ[
            "SIGNALDESK_SERVE_FRONTEND"
        ].lower() == "true"
    if os.environ.get("SIGNALDESK_REQUIRE_BASIC_AUTH"):
        raw["deployment"]["require_basic_auth"] = os.environ[
            "SIGNALDESK_REQUIRE_BASIC_AUTH"
        ].lower() == "true"
    if os.environ.get("SIGNALDESK_AUTO_WARMUP"):
        raw["nse_mcp"]["automatic_history_warmup_enabled"] = os.environ[
            "SIGNALDESK_AUTO_WARMUP"
        ].lower() == "true"
    if os.environ.get("SIGNALDESK_BOOTSTRAP_UNIVERSE"):
        raw["nse_mcp"]["bootstrap_candidate_on_startup"] = os.environ[
            "SIGNALDESK_BOOTSTRAP_UNIVERSE"
        ].lower() == "true"
    if os.environ.get("SIGNALDESK_PUBLIC_ORIGIN"):
        raw["runtime"]["allowed_origins"] = [os.environ["SIGNALDESK_PUBLIC_ORIGIN"]]
    if os.environ.get("PORT"):
        raw["runtime"]["api_port"] = int(os.environ["PORT"])
    if os.environ.get("SIGNALDESK_API_HOST"):
        raw["runtime"]["api_host"] = os.environ["SIGNALDESK_API_HOST"]
    settings = AppSettings.model_validate(raw)
    settings.runtime.database_path = root / settings.runtime.database_path
    settings.runtime.demo_data_path = root / settings.runtime.demo_data_path
    settings.runtime.strategy_fixture_path = root / settings.runtime.strategy_fixture_path
    settings.runtime.replay_data_path = root / settings.runtime.replay_data_path
    settings.runtime.exit_replay_data_path = root / settings.runtime.exit_replay_data_path
    settings.angel_one.instruments_path = root / settings.angel_one.instruments_path
    settings.nse_mcp.universe_path = root / settings.nse_mcp.universe_path
    settings.nse_mcp.universe_candidate_path = root / settings.nse_mcp.universe_candidate_path
    settings.nse_mcp.promoted_universe_path = root / settings.nse_mcp.promoted_universe_path
    settings.nse_mcp.previous_universe_path = root / settings.nse_mcp.previous_universe_path
    settings.nse_mcp.cache_path = root / settings.nse_mcp.cache_path
    settings.exchange_calendar.path = root / settings.exchange_calendar.path
    settings.corporate_actions.cache_path = root / settings.corporate_actions.cache_path
    state_directory = os.environ.get("SIGNALDESK_STATE_DIR")
    if state_directory:
        state = Path(state_directory).resolve()
        settings.runtime.database_path = state / "signaldesk.db"
        settings.nse_mcp.universe_candidate_path = state / "nifty-500-universe-candidate.json"
        settings.nse_mcp.promoted_universe_path = state / "nse-universe-active.json"
        settings.nse_mcp.previous_universe_path = state / "nse-universe-previous.json"
        settings.nse_mcp.cache_path = state / "nse-mcp-cache.json"
        settings.corporate_actions.cache_path = state / "nse-corporate-actions.json"
    if settings.nse_mcp.promoted_universe_path.exists():
        promoted = json.loads(
            settings.nse_mcp.promoted_universe_path.read_text(encoding="utf-8")
        )
        version = str(promoted.get("version", "")).strip()
        if not version:
            raise ValueError("Promoted NSE universe version is missing")
        settings.scanning.universe_version = version
    return settings
