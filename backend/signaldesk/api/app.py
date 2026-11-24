import asyncio
import base64
import os
import secrets
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from signaldesk.application import (
    DashboardService,
    DailyBriefService,
    HistoryWarmupWorker,
    PerformanceValidationService,
    PaperExecutionError,
    PaperExecutionService,
    PaperOrderError,
    PaperOrderService,
    PositionExitError,
    PositionExitService,
    ScanError,
    ScanService,
    ScanScheduler,
    StrategyResearchProvider,
    SystemStatusService,
)
from signaldesk.config import AppSettings, load_settings
from signaldesk.domain.models import (
    DashboardPayload,
    DailyBriefPayload,
    ExitReplayResult,
    MarketDataWarmupStatus,
    PaperAccountPayload,
    PerformanceValidationPayload,
    PortfolioAnalysisPayload,
    PaperOrder,
    PaperOrderRequest,
    ReplayResult,
    ScanHistoryPayload,
    ScanRun,
    SchedulerStatus,
    PublicSettingsPayload,
    SystemHealthPayload,
    UniversePromotionRequest,
    UniversePromotionStatus,
)
from signaldesk.infrastructure import (
    AngelOneCredentials,
    CorporateActionError,
    JsonTradingCalendar,
    JsonExitReplayProvider,
    JsonReplayProvider,
    NseMcpDailyBarProvider,
    NseMcpError,
    NseUniverseSynchronizer,
    NseUniversePromotionService,
    SqlitePaperOrderRepository,
    SqliteScanRepository,
    UniversePromotionError,
    angel_one_credential_readiness,
    build_daily_bar_provider_with_credentials,
)


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    settings = load_settings(config_path)
    if (
        settings.providers.market_data == "nse_mcp"
        and settings.nse_mcp.bootstrap_candidate_on_startup
        and not settings.nse_mcp.universe_candidate_path.exists()
    ):
        NseUniverseSynchronizer(settings.nse_mcp).sync_candidate()
    angel_credentials = AngelOneCredentials.from_environment()
    market_data = build_daily_bar_provider_with_credentials(settings, angel_credentials)
    research = StrategyResearchProvider(
        settings, settings.runtime.demo_data_path, market_data
    )
    repository = SqlitePaperOrderRepository(settings.runtime.database_path)
    scan_repository = SqliteScanRepository(settings.runtime.database_path)
    replay = JsonReplayProvider(settings.runtime.replay_data_path)
    exit_replay = JsonExitReplayProvider(settings.runtime.exit_replay_data_path)
    orders = PaperOrderService(settings, research, repository)
    execution = PaperExecutionService(settings, replay, repository)
    position_exits = PositionExitService(settings, exit_replay, repository)
    dashboard_service = DashboardService(settings, research, repository)
    scans = ScanService(settings, research, scan_repository)
    daily_brief = DailyBriefService(
        settings, research, repository, scans, scan_repository
    )
    performance_validation = PerformanceValidationService(settings, repository)
    calendar = JsonTradingCalendar(settings.exchange_calendar.path)
    scheduler = ScanScheduler(settings, scans, scan_repository, calendar)
    system_status = SystemStatusService(
        settings,
        research,
        market_data,
        repository,
        scan_repository,
        scheduler,
        angel_one_credential_readiness(angel_credentials, market_data),
    )
    universe_promotion = NseUniversePromotionService(settings)
    warmup_worker = (
        HistoryWarmupWorker(settings.nse_mcp, market_data)
        if isinstance(market_data, NseMcpDailyBarProvider)
        and settings.nse_mcp.automatic_history_warmup_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        repository.initialize()
        scan_repository.initialize()
        repository.backfill_positions(settings.paper_execution.tp1_fraction)
        scheduler_task = asyncio.create_task(scheduler.run_forever())
        warmup_task = (
            asyncio.create_task(warmup_worker.run_forever())
            if warmup_worker is not None
            else None
        )
        try:
            yield
        finally:
            scheduler_task.cancel()
            if warmup_task is not None:
                warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
            if warmup_task is not None:
                with suppress(asyncio.CancelledError):
                    await warmup_task

    app = FastAPI(
        title="SignalDesk Private API",
        version=settings.schema_version,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.research = research
    app.state.market_data = market_data
    app.state.paper_orders = orders
    app.state.paper_order_repository = repository
    app.state.dashboard_service = dashboard_service
    app.state.paper_execution = execution
    app.state.position_exits = position_exits
    app.state.scans = scans
    app.state.daily_brief = daily_brief
    app.state.performance_validation = performance_validation
    app.state.scheduler = scheduler
    app.state.system_status = system_status
    app.state.universe_promotion = universe_promotion
    username = os.environ.get("SIGNALDESK_BASIC_AUTH_USERNAME", "")
    password = os.environ.get("SIGNALDESK_BASIC_AUTH_PASSWORD", "")
    if settings.deployment.environment == "production":
        if not os.environ.get("SIGNALDESK_STATE_DIR"):
            raise ValueError("Production requires SIGNALDESK_STATE_DIR")
        if settings.deployment.require_basic_auth and (not username or not password):
            raise ValueError("Production basic authentication credentials are missing")

    @app.middleware("http")
    async def private_access(request: Request, call_next):
        if (
            not settings.deployment.require_basic_auth
            or request.url.path == "/api/health"
        ):
            return await call_next(request)
        authorization = request.headers.get("Authorization", "")
        valid = False
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(authorization[6:]).decode("utf-8")
                supplied_username, supplied_password = decoded.split(":", 1)
                valid = secrets.compare_digest(supplied_username, username) and secrets.compare_digest(
                    supplied_password, password
                )
            except (ValueError, UnicodeDecodeError):
                valid = False
        if not valid:
            return JSONResponse(
                {"detail": "Private SignalDesk authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="SignalDesk Private"'},
            )
        return await call_next(request)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.runtime.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    @app.get("/api/health")
    def health(request: Request) -> dict:
        current: AppSettings = request.app.state.settings
        return {
            "status": "ok",
            "mode": current.mode,
            "live_execution_enabled": current.execution.live_enabled,
            "schema_version": current.schema_version,
            "environment": current.deployment.environment,
        }

    @app.get("/api/dashboard", response_model=DashboardPayload)
    def dashboard(request: Request) -> DashboardPayload:
        return request.app.state.dashboard_service.view()

    @app.get("/api/paper/orders", response_model=list[PaperOrder])
    def list_paper_orders(request: Request) -> list[PaperOrder]:
        return request.app.state.paper_order_repository.list_orders()

    @app.get("/api/paper/account", response_model=PaperAccountPayload)
    def paper_account(request: Request) -> PaperAccountPayload:
        return request.app.state.dashboard_service.paper_account()

    @app.get("/api/scans/history", response_model=ScanHistoryPayload)
    def scan_history(request: Request) -> ScanHistoryPayload:
        return request.app.state.scans.history()

    @app.get("/api/mvp/daily-brief", response_model=DailyBriefPayload)
    def mvp_daily_brief(request: Request) -> DailyBriefPayload:
        return request.app.state.daily_brief.brief()

    @app.post("/api/mvp/run", response_model=DailyBriefPayload)
    def run_mvp_analysis(request: Request) -> DailyBriefPayload:
        try:
            return request.app.state.daily_brief.run()
        except ScanError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/portfolio/analysis", response_model=PortfolioAnalysisPayload)
    def portfolio_analysis(request: Request) -> PortfolioAnalysisPayload:
        return request.app.state.daily_brief.portfolio()

    @app.get(
        "/api/validation/performance",
        response_model=PerformanceValidationPayload,
    )
    def performance_validation_report(
        request: Request,
    ) -> PerformanceValidationPayload:
        return request.app.state.performance_validation.report()

    @app.post("/api/scans/archive", response_model=ScanRun)
    def archive_scan(request: Request) -> ScanRun:
        try:
            return request.app.state.scans.archive_current()
        except ScanError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/scheduler/status", response_model=SchedulerStatus)
    def scheduler_status(request: Request) -> SchedulerStatus:
        return request.app.state.scheduler.status()

    @app.get("/api/market-data/warmup", response_model=MarketDataWarmupStatus)
    def market_data_warmup(request: Request) -> MarketDataWarmupStatus:
        provider = request.app.state.market_data
        if isinstance(provider, NseMcpDailyBarProvider):
            return provider.warmup_status()
        return MarketDataWarmupStatus(
            available=False,
            totalSymbols=0,
            warmedSymbols=0,
            remainingSymbols=0,
            batchSize=request.app.state.settings.nse_mcp.history_warmup_batch_size,
            activeUniverseSymbols=0,
            failedSymbols=[],
            readyToActivate=False,
        )

    @app.post("/api/market-data/warmup/advance", response_model=MarketDataWarmupStatus)
    def advance_market_data_warmup(request: Request) -> MarketDataWarmupStatus:
        provider = request.app.state.market_data
        if not isinstance(provider, NseMcpDailyBarProvider):
            raise HTTPException(status_code=409, detail="NSE MCP is not selected")
        try:
            return provider.warmup_next_batch()
        except NseMcpError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/market-data/promotion", response_model=UniversePromotionStatus)
    def universe_promotion_status(request: Request) -> UniversePromotionStatus:
        return request.app.state.universe_promotion.status()

    @app.post(
        "/api/market-data/promotion/refresh",
        response_model=UniversePromotionStatus,
    )
    def refresh_universe_promotion(request: Request) -> UniversePromotionStatus:
        try:
            return request.app.state.universe_promotion.refresh_evidence()
        except (CorporateActionError, UniversePromotionError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/api/market-data/promotion/prepare",
        response_model=UniversePromotionStatus,
    )
    def prepare_universe_promotion(
        payload: UniversePromotionRequest, request: Request
    ) -> UniversePromotionStatus:
        try:
            return request.app.state.universe_promotion.promote(
                payload.candidate_version
            )
        except UniversePromotionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/settings/public", response_model=PublicSettingsPayload)
    def public_settings(request: Request) -> PublicSettingsPayload:
        return request.app.state.system_status.public_settings()

    @app.get("/api/system/health", response_model=SystemHealthPayload)
    def system_health(request: Request) -> SystemHealthPayload:
        return request.app.state.system_status.health()

    @app.post(
        "/api/paper/orders",
        response_model=PaperOrder,
        status_code=status.HTTP_201_CREATED,
    )
    def create_paper_order(
        payload: PaperOrderRequest, request: Request
    ) -> PaperOrder:
        try:
            return request.app.state.paper_orders.create(payload)
        except PaperOrderError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/paper/orders/{order_id}/replay/advance",
        response_model=ReplayResult,
    )
    def advance_replay(order_id: str, request: Request) -> ReplayResult:
        try:
            return request.app.state.paper_execution.advance(order_id)
        except PaperExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/paper/orders/{order_id}/cancel",
        response_model=PaperOrder,
    )
    def cancel_paper_order(order_id: str, request: Request) -> PaperOrder:
        try:
            return request.app.state.paper_execution.cancel(order_id)
        except PaperExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/paper/positions/{position_id}/replay/advance",
        response_model=ExitReplayResult,
    )
    def advance_exit_replay(position_id: str, request: Request) -> ExitReplayResult:
        try:
            return request.app.state.position_exits.advance(position_id)
        except PositionExitError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    if settings.deployment.serve_frontend:
        frontend = Path(__file__).resolve().parents[3] / "dist"
        index = frontend / "index.html"
        assets = frontend / "assets"
        if not index.exists() or not assets.exists():
            raise ValueError("Production frontend build is missing; run npm run build")
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend_route(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            return FileResponse(index)

    return app
