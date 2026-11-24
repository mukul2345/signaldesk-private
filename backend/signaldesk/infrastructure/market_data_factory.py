from signaldesk.config import AppSettings
from signaldesk.domain.ports import DailyBarProvider

from .angel_one_market_data import AngelOneCredentials, AngelOneDailyBarProvider
from .nse_mcp_market_data import NseMcpDailyBarProvider
from .scenario_market_data import ScenarioDailyBarProvider


def build_daily_bar_provider(settings: AppSettings) -> DailyBarProvider:
    return build_daily_bar_provider_with_credentials(
        settings, AngelOneCredentials.from_environment()
    )


def build_daily_bar_provider_with_credentials(
    settings: AppSettings, credentials: AngelOneCredentials
) -> DailyBarProvider:
    selected = settings.providers.market_data
    if selected == "strategy_fixture":
        return ScenarioDailyBarProvider(settings.runtime.strategy_fixture_path)
    if selected == "nse_mcp":
        return NseMcpDailyBarProvider(
            settings.nse_mcp,
            required_bars=settings.strategy.warmup_bars,
            corporate_action_settings=settings.corporate_actions,
        )
    if selected == "angel_one":
        return AngelOneDailyBarProvider(settings.angel_one, credentials)
    raise ValueError(f"Unsupported market-data provider: {selected}")
