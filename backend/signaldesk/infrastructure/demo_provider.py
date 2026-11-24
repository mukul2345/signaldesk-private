import json
from pathlib import Path
from typing import Optional

from signaldesk.domain.models import Candidate, DashboardPayload


class JsonResearchProvider:
    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path

    def dashboard(self) -> DashboardPayload:
        payload = json.loads(self._source_path.read_text(encoding="utf-8"))
        return DashboardPayload.model_validate(payload)

    def candidate(self, candidate_id: str) -> Optional[Candidate]:
        return next(
            (item for item in self.dashboard().candidates if item.id == candidate_id),
            None,
        )
