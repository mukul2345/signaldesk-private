# Private MVP deployment

## Supported production shape

Deploy the repository as one long-running Docker service with a persistent volume mounted at `/data`. The container serves the compiled React application and FastAPI from the same origin, runs the 18:30 Asia/Kolkata scheduler, persists the paper ledger and scan history, bootstraps the validated Nifty 500 candidate on first start and resumes history warm-up in rate-limited batches.

Vercel may host a frontend preview, but Vercel Functions alone are not the supported production runtime for this release because the application owns an always-on scheduler and SQLite/WAL state. The tracked `vercel.json` builds the static preview only.

## Required secrets and settings

Create a persistent disk and configure the variables shown in `.env.production.example`. Set strong unique values for:

- `SIGNALDESK_BASIC_AUTH_USERNAME`
- `SIGNALDESK_BASIC_AUTH_PASSWORD`
- `SIGNALDESK_PUBLIC_ORIGIN`

Do not store populated secret files in Git. Keep `SIGNALDESK_STATE_DIR=/data`, mount the disk there and configure the provider to retain or snapshot that volume.

## Build and start

```bash
docker build -t signaldesk-private .
docker run --rm \
  --env-file .env.production \
  --mount type=volume,src=signaldesk-data,dst=/data \
  -p 8000:8000 \
  signaldesk-private
```

The health check is intentionally unauthenticated and exposes only mode, schema version and environment:

```text
GET /api/health
```

Every UI and business API route requires HTTP Basic authentication in production. The service refuses to start without a persistent state directory or authentication credentials.

## First deployment lifecycle

1. The service downloads and validates the official Nifty 500 constituent CSV when the persistent candidate is absent.
2. The five-stock pilot remains active while background warm-up retrieves candidate history in configured batches.
3. Settings & Health displays progress, failures and every promotion gate.
4. Refresh corporate-action evidence after warm-up. Rights issues, demergers and unparseable actions remain blocked until an authoritative adjusted-price source is configured.
5. Prepare promotion only when every gate passes, then restart the service. The previous universe is retained on the persistent disk.

The deployed pilot is functional before full-universe promotion. It must never claim that five trades will exist each day; zero qualified setups is a valid output.

## Release verification

- `/api/health` returns HTTP 200 without credentials.
- `/` and business APIs return HTTP 401 without credentials.
- Authenticated `/` serves the compiled dashboard.
- Authenticated `/api/mvp/run` archives an idempotent completed scan and returns the shortlist plus portfolio analysis.
- `/data/signaldesk.db` and `/data/nse-mcp-cache.json` survive a service restart.
- The hosting provider has volume backup or snapshot retention enabled.

Real broker orders remain disabled and are not part of this deployment.
