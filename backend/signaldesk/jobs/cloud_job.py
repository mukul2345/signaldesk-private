"""Idempotent cloud-job dispatcher; business job adapters are promoted one at a time."""
from __future__ import annotations

import os
import socket
from datetime import datetime, timezone

from signaldesk.application.cloud_jobs import deliver_notifications, observe_paper_positions, retention_and_health, review_portfolio, run_daily_scan
from signaldesk.infrastructure.supabase_rest import SupabaseRest


SUPPORTED = {"daily-scan", "paper-observation", "portfolio-review", "notification-delivery", "retention"}


def main() -> None:
    job = os.environ.get("JOB_NAME", "daily-scan")
    if job not in SUPPORTED:
        raise SystemExit(f"Unsupported JOB_NAME: {job}")
    owner_id = os.environ.get("SIGNALDESK_OWNER_ID", "")
    if not owner_id:
        raise SystemExit("SIGNALDESK_OWNER_ID is required")
    client = SupabaseRest.service()
    claimed = client.request(
        "POST",
        "rpc/claim_scheduled_job",
        json={"p_job_key": job, "p_worker": socket.gethostname(), "p_lease_seconds": 1800},
    )
    if not claimed:
        print(f"Skipped {job}: already claimed or disabled")
        return
    handlers = {
        "daily-scan": run_daily_scan,
        "paper-observation": observe_paper_positions,
        "portfolio-review": review_portfolio,
        "notification-delivery": deliver_notifications,
        "retention": retention_and_health,
    }
    try:
        result = handlers[job](client)
        client.update("scheduled_jobs", {"last_status": "COMPLETE", "last_completed_at": datetime.now(timezone.utc).isoformat(), "lease_owner": None, "lease_expires_at": None, "last_error": None}, {"job_key": f"eq.{job}"})
        print(result)
    except Exception as error:
        client.update("scheduled_jobs", {"last_status": "FAILED", "lease_owner": None, "lease_expires_at": None, "last_error": str(error)[:500]}, {"job_key": f"eq.{job}"})
        try:
            client.upsert("system_health", {"component": f"job:{job}", "status": "ERROR", "checked_at": datetime.now(timezone.utc).isoformat(), "details": {"error": str(error)[:500]}}, on_conflict="component")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
