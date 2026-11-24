import sys

import httpx

from signaldesk.config import load_settings


def main() -> int:
    settings = load_settings()
    url = f"http://{settings.runtime.api_host}:{settings.runtime.api_port}/api/mvp/run"
    try:
        response = httpx.post(url, timeout=settings.nse_mcp.request_timeout_seconds)
        response.raise_for_status()
        brief = response.json()
    except (httpx.HTTPError, ValueError) as error:
        print(f"SignalDesk daily analysis failed: {error}", file=sys.stderr)
        print("Start the API with `npm run api`, then retry.", file=sys.stderr)
        return 1
    print(brief["message"])
    for index, setup in enumerate(brief["topSetups"], start=1):
        print(
            f"{index}. {setup['symbol']} {setup['state']} | "
            f"Entry {setup['entry']:.2f} | SL {setup['stop']:.2f} | "
            f"TP1 {setup['targetOne']:.2f} | TP2 {setup['targetTwo']:.2f}"
        )
    portfolio = brief["portfolio"]
    print(
        f"Portfolio {portfolio['health']} | Open {portfolio['openPositions']} | "
        f"Market value {portfolio['marketValue']:.2f} | "
        f"Unrealized P&L {portfolio['unrealizedPnl']:.2f} | "
        f"Reserved risk {portfolio['reservedRisk']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
