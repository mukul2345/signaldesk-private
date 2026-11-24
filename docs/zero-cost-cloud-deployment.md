# Zero-cost cloud deployment

## Current readiness

The repository now contains the cloud database contract, RLS policies, stateless
Vercel API, secured Telegram webhook, authenticated frontend, GitHub CI, leased job
dispatcher, Supabase scanner persistence, genuine forward-paper observation,
portfolio reviews, notification delivery, and retention/health monitoring. SQLite
remains available only for the local development runtime.

This remains a paper-trading research tool. A 30% monthly return is an aspirational
comparison threshold, never a promise or an optimization target.

## Mandatory secret reset

The previously shared Supabase secret key must be revoked and replaced in the
Supabase dashboard. Never put it in `.env.example`, frontend variables, screenshots,
logs, or Git history. Only Vercel server functions and GitHub Actions may receive it.

## Supabase

1. Rotate the secret key.
2. Link the Supabase CLI to the project and apply all migrations in order from
   `supabase/migrations/`.
3. Create the one private user in Supabase Auth and record its UUID as
   `SIGNALDESK_OWNER_ID`.
   In **Authentication → Users**, use **Add user → Create new user**, enter the
   same email/password used at the SignalDesk sign-in page, and mark the email as
   confirmed. Then run this once in Supabase SQL Editor, substituting the UUID:

   ```sql
   insert into public.risk_settings(owner_id, capital, risk_per_trade_pct, max_open_positions, max_portfolio_risk_pct)
   values ('YOUR_AUTH_USER_UUID', 50000, 1, 5, 5)
   on conflict (owner_id) do update set capital = excluded.capital;
   ```

   Migration `202611240003_auth_user_profile.sql` automatically creates this
   default risk record for every subsequently created Auth user; the SQL above is
   only needed for a user created before that migration is applied.

   The browser uses only `VITE_SUPABASE_URL` and
   `VITE_SUPABASE_PUBLISHABLE_KEY`. `SUPABASE_SECRET_KEY` is server-only and
   must never be a Vite-prefixed value.
4. Review the seeded rows in `scheduled_jobs` and enable each only after its first
   controlled manual run succeeds.
5. Confirm RLS with both the authenticated user and an anonymous client. Service
   role access bypasses RLS and must stay server-side.

## Vercel

Import the GitHub repository and configure the repository root. Add these encrypted
server variables: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
`SUPABASE_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`,
`TELEGRAM_ALLOWED_CHAT_ID`, and `PUBLIC_APP_URL`. Only variables deliberately
prefixed for Vite are embedded in the browser; never prefix a secret.

The Vercel function exposes authenticated cloud dashboard, paper-account,
portfolio, performance, transaction and Telegram endpoints. Long scans do not run
inside Vercel functions.

Use these import settings:

- Root Directory: `./`
- Framework Preset: `Vite`
- Install Command: `npm ci`
- Build Command: `npm run build`
- Output Directory: `dist`

Do not commit a populated `.env` file. Vercel environment variables are configured
in its dashboard; `.env.example` documents their names only.

## Signup and password recovery

The login page supports sign-in, password recovery, recovery-password update, and
optional registration. Registration remains disabled by default with
`VITE_ALLOW_SIGNUP=false`; set it to `true` only when public account creation is
intended, then redeploy. In Supabase **Auth → URL Configuration**, set the Site URL
to the Vercel production URL and add the production URL plus
`http://127.0.0.1:4173` to the Redirect URLs allow list. Keep email confirmation
enabled so a new user must verify their address before sign-in.

## GitHub Actions

Add `SUPABASE_URL`, the newly rotated `SUPABASE_SECRET_KEY`, and
`SIGNALDESK_OWNER_ID` as repository Actions secrets. CI is safe to enable now.
Keep the repository variable `CLOUD_JOBS_ENABLED` unset or `false` until all job
adapters pass integration tests. Scheduled runs are gated by this variable; manual
dispatch remains available for controlled validation.
The workflow runs a `market-cycle` every 15 minutes from 09:15 through 15:30 IST
and an `eod-cycle` at 18:30 IST on weekdays. GitHub schedules can be delayed, so
every operation uses database idempotency and persisted timestamps rather than
assuming exact invocation time.
For a truly zero-cost private repository, watch the included Actions-minute quota;
public repositories get standard hosted runners free, while private repositories
have a monthly allowance.

## Telegram

Create a bot with BotFather, send `/start` to it, obtain the numeric chat ID, and
generate a long random webhook secret. Register:

```text
https://api.telegram.org/bot<TOKEN>/setWebhook
  url=https://<deployment>/api/telegram/webhook
  secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

The handler validates Telegram's secret header and optionally locks all commands to
`TELEGRAM_ALLOWED_CHAT_ID`. It never authenticates by mutable username.

## Remaining deployment gates

- rotate the exposed Supabase secret and apply all migrations
- create the private Supabase Auth user and seed its `risk_settings` row
- run an integration test against the real Supabase project
- validate the permitted market-data source and Angel One daily authentication
- add GitHub repository secrets and manually validate every cloud job
- register the Telegram webhook and verify its numeric chat restriction
- create the GitHub repository, push, connect Vercel, then run deployment smoke tests

The application code is prepared for these gates, but production cannot be claimed
until the external services and genuine live-paper observations have been verified.
