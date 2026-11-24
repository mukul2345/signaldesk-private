from signaldesk.config import load_settings
from signaldesk.infrastructure import NseUniverseSynchronizer


def main() -> None:
    settings = load_settings()
    payload = NseUniverseSynchronizer(settings.nse_mcp).sync_candidate()
    print(
        "Validated Nifty 500 candidate: "
        f"{len(payload['instruments'])} symbols -> "
        f"{settings.nse_mcp.universe_candidate_path}"
    )


if __name__ == "__main__":
    main()
