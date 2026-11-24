from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from signaldesk.config import AppSettings
from signaldesk.domain.models import DailyBar, PromotionCheck, UniversePromotionStatus

from .corporate_action_adjustment import CorporateActionAdjuster
from .nse_corporate_actions import NseCorporateActionClient


class UniversePromotionError(RuntimeError):
    pass


class NseUniversePromotionService:
    def __init__(
        self,
        settings: AppSettings,
        corporate_actions: Optional[NseCorporateActionClient] = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._settings = settings
        self._corporate_actions = corporate_actions or NseCorporateActionClient(
            settings.corporate_actions
        )
        self._adjuster = CorporateActionAdjuster(settings.corporate_actions)
        self._now = now
        self._runtime_active_version = settings.scanning.universe_version

    @staticmethod
    def _read(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise UniversePromotionError(f"Promotion input is unreadable: {path.name}") from error
        if not isinstance(payload, dict):
            raise UniversePromotionError(f"Promotion input is invalid: {path.name}")
        return payload

    @staticmethod
    def _write_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def refresh_evidence(self) -> UniversePromotionStatus:
        self._corporate_actions.sync()
        return self.status()

    def _prepared_version(self) -> Optional[str]:
        prepared = self._read(self._settings.nse_mcp.promoted_universe_path)
        return str(prepared.get("version")) if prepared else None

    def status(self) -> UniversePromotionStatus:
        candidate = self._read(self._settings.nse_mcp.universe_candidate_path)
        if candidate is None:
            return UniversePromotionStatus(
                candidateAvailable=False,
                runtimeActiveVersion=self._runtime_active_version,
                preparedVersion=self._prepared_version(),
                totalSymbols=0,
                warmedSymbols=0,
                corporateActionsFresh=False,
                blockingActionCount=0,
                blockingActionSymbols=[],
                adjustedActionCount=0,
                adjustedActionSymbols=[],
                priceAnomalyCount=0,
                priceAnomalySymbols=[],
                staleHistoryCount=0,
                staleHistorySymbols=[],
                eligibleToPromote=False,
                restartRequired=False,
                checks=[],
            )
        version = str(candidate.get("version", "")).strip()
        instruments = candidate.get("instruments", [])
        if not version or not isinstance(instruments, list):
            raise UniversePromotionError("Candidate universe metadata is invalid")
        symbols = [str(item.get("symbol", "")).strip().upper() for item in instruments]
        if not symbols or len(symbols) != len(set(symbols)) or any(not item for item in symbols):
            raise UniversePromotionError("Candidate universe symbols are invalid")
        cache = self._read(self._settings.nse_mcp.cache_path) or {"bars": {}}
        bars_by_symbol = cache.get("bars", {})
        required = self._settings.strategy.warmup_bars
        complete = {
            symbol: bars_by_symbol.get(symbol, [])
            for symbol in symbols
            if len(bars_by_symbol.get(symbol, [])) >= required
        }
        latest_by_symbol = {
            symbol: str(rows[-1]["session"])
            for symbol, rows in complete.items()
            if rows
        }
        latest_session = max(latest_by_symbol.values()) if latest_by_symbol else None
        stale = sorted(
            symbol
            for symbol, session in latest_by_symbol.items()
            if latest_session is not None and session != latest_session
        )

        action_cache = self._read(self._settings.corporate_actions.cache_path)
        action_fresh = False
        checked_at = None
        actions = []
        if action_cache:
            checked_text = action_cache.get("fetched_at")
            if checked_text:
                checked_at = datetime.fromisoformat(str(checked_text))
                age = self._now().astimezone(timezone.utc) - checked_at.astimezone(timezone.utc)
                action_fresh = age.total_seconds() <= self._settings.corporate_actions.cache_ttl_seconds
            actions = action_cache.get("actions", [])
        blocking = set()
        adjusted = set()
        reconciled = {}
        for symbol, rows in complete.items():
            result = self._adjuster.adjust(
                symbol,
                [DailyBar.model_validate(row) for row in rows],
                actions=actions,
            )
            reconciled[symbol] = result.bars
            if result.applied:
                adjusted.add(symbol)
            if result.unresolved_subjects:
                blocking.add(symbol)

        maximum_gap = self._settings.corporate_actions.maximum_unexplained_gap_percent
        anomalies = set()
        for symbol, rows in reconciled.items():
            for previous, current in zip(rows, rows[1:]):
                gap = abs(current.open / previous.close - 1) * 100
                if gap > maximum_gap:
                    anomalies.add(symbol)
                    break
        expected_count = (
            self._settings.nse_mcp.universe_expected_minimum
            <= len(symbols)
            <= self._settings.nse_mcp.universe_expected_maximum
        )
        history_complete = len(complete) == len(symbols)
        limit = self._settings.corporate_actions.report_symbol_limit
        checks = [
            PromotionCheck(
                id="constituents",
                label="Validated constituent count",
                status="PASS" if expected_count else "BLOCKED",
                detail=f"{len(symbols)} symbols within configured bounds",
            ),
            PromotionCheck(
                id="history",
                label="Completed daily history",
                status="PASS" if history_complete else "PENDING",
                detail=f"{len(complete)} of {len(symbols)} symbols warmed",
            ),
            PromotionCheck(
                id="session_alignment",
                label="Latest-session alignment",
                status="PASS" if history_complete and not stale else "PENDING",
                detail=(
                    f"All histories end on {latest_session}"
                    if history_complete and not stale
                    else f"{len(stale)} histories are behind the latest cached session"
                    if history_complete
                    else "Waiting for complete history"
                ),
            ),
            PromotionCheck(
                id="corporate_actions",
                label="Corporate-action review",
                status=(
                    "BLOCKED"
                    if blocking
                    else "PASS"
                    if action_fresh and history_complete
                    else "PENDING"
                ),
                detail=(
                    f"{len(blocking)} symbols require an authoritative adjusted-price source"
                    if blocking
                    else f"{len(adjusted)} symbol histories adjusted deterministically"
                    if action_fresh and history_complete
                    else "Waiting for complete history before final reconciliation"
                    if action_fresh
                    else "Refresh official NSE corporate-action evidence"
                ),
            ),
            PromotionCheck(
                id="price_continuity",
                label="Price continuity",
                status="PASS" if history_complete and not anomalies else "BLOCKED" if anomalies else "PENDING",
                detail=(
                    f"{len(anomalies)} symbols exceed the configured gap threshold"
                    if anomalies
                    else "No unexplained price discontinuities detected"
                    if history_complete
                    else "Waiting for complete history"
                ),
            ),
        ]
        eligible = all(item.status == "PASS" for item in checks)
        prepared = self._prepared_version()
        return UniversePromotionStatus(
            candidateAvailable=True,
            candidateVersion=version,
            runtimeActiveVersion=self._runtime_active_version,
            preparedVersion=prepared,
            totalSymbols=len(symbols),
            warmedSymbols=len(complete),
            latestSession=latest_session,
            corporateActionsFresh=action_fresh,
            corporateActionsCheckedAt=checked_at,
            blockingActionCount=len(blocking),
            blockingActionSymbols=sorted(blocking)[:limit],
            adjustedActionCount=len(adjusted),
            adjustedActionSymbols=sorted(adjusted)[:limit],
            priceAnomalyCount=len(anomalies),
            priceAnomalySymbols=sorted(anomalies)[:limit],
            staleHistoryCount=len(stale),
            staleHistorySymbols=stale[:limit],
            eligibleToPromote=eligible,
            restartRequired=prepared is not None and prepared != self._runtime_active_version,
            checks=checks,
        )

    def promote(self, candidate_version: str) -> UniversePromotionStatus:
        report = self.status()
        if report.candidate_version != candidate_version:
            raise UniversePromotionError("Candidate version changed; refresh the promotion report")
        if not report.eligible_to_promote:
            raise UniversePromotionError("Candidate universe has not passed every promotion gate")
        candidate = self._read(self._settings.nse_mcp.universe_candidate_path)
        if candidate is None:
            raise UniversePromotionError("Candidate universe is unavailable")
        current_path = (
            self._settings.nse_mcp.promoted_universe_path
            if self._settings.nse_mcp.promoted_universe_path.exists()
            else self._settings.nse_mcp.universe_path
        )
        current = self._read(current_path)
        if current is not None:
            self._write_atomic(self._settings.nse_mcp.previous_universe_path, current)
        promoted = dict(candidate)
        promoted["promoted_at"] = self._now().astimezone(timezone.utc).isoformat()
        promoted["previous_version"] = self._runtime_active_version
        promoted["promotion_evidence"] = {
            "latest_session": report.latest_session.isoformat() if report.latest_session else None,
            "corporate_actions_checked_at": report.corporate_actions_checked_at.isoformat()
            if report.corporate_actions_checked_at
            else None,
            "blocking_action_count": report.blocking_action_count,
            "adjusted_action_count": report.adjusted_action_count,
            "price_anomaly_count": report.price_anomaly_count,
            "stale_history_count": report.stale_history_count,
        }
        self._write_atomic(self._settings.nse_mcp.promoted_universe_path, promoted)
        return self.status()
