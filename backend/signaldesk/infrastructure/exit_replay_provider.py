import json
from pathlib import Path
from typing import Dict, List, Optional

from signaldesk.domain.models import ExitReplayObservation


class JsonExitReplayProvider:
    def __init__(self, source_path: Path) -> None:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        self._observations: Dict[str, List[dict]] = raw

    def observation(
        self, symbol: str, sequence: int
    ) -> Optional[ExitReplayObservation]:
        items = self._observations.get(symbol, [])
        if sequence >= len(items):
            return None
        return ExitReplayObservation(
            symbol=symbol,
            sequence=sequence,
            **items[sequence],
        )

    def count(self, symbol: str) -> int:
        return len(self._observations.get(symbol, []))
