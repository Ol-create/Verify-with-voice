# TrueVoice2 Roadmap: Admin App, Company Subscriptions, Business Mobile App

## Where Truevoice2 stands today

| Area | Status |
|---|---|
| Companies | `companies` with `status` (pending/active/suspended) and `email`; several revocable keys per company in `api_credentials`, stored as SHA-256 hashes |
| Company onboarding | CLI only: `python -m scripts.manage_company create/add-key/list-keys/revoke-key/rotate/suspend/activate` |
| End users | `users` table, one row per (company, external_user_id), with language |
| Tokens | `POST /v1/token` (X-API-KEY + X-API-SECRET), `/v1/token/refresh`, `/v1/token/revoke`; access tokens carry `type=access`, `user_id`, `company_id` |
| Voice | `GET /v1/challenge` → `POST /v1/enroll-voice` (3 samples, averaged) → `POST /v1/secure-verify-voice`; AASIST anti-spoofing; Whisper transcription; ECAPA embeddings |
| Rate limiting | slowapi, per company (falls back to per IP), `RATE_LIMIT` setting |
| Schema | Alembic owns it; `create_all` removed |
| Tests | 51 tests in `tests/`, everything external mocked; CI runs them |
| Deploy | AWS Lambda via Mangum (`handler` in `app/main.py`); DB moving to Supabase (branch `feat/add-supabaseDB`) |

**Missing for a paid product:** plans, subscriptions, usage metering, quotas, admin accounts, a self-service portal, and payments.

## Target architecture

```
                ┌───────────────────────┐
 Admin (web) ──▶│  /admin/*             │  onboard companies, plans, keys, usage
                │                       │
 Business  ────▶│  /portal/*            │  sign up, buy plan, manage keys, test voice
 mobile app     │                       │
                │  FastAPI (Truevoice2) │──▶ Postgres/Supabase, S3, OpenAI, ECAPA, AASIST
 Business's ───▶│  /v1/*                │  token, challenge, enroll, verify (metered)
 own backend    └───────────────────────┘
```

**Security rule for every client:** API key + secret never ship inside a mobile app or browser. A business's real app calls *its own backend*, which calls `POST /v1/token` and passes the user's access/refresh tokens to the app. The TrueVoice mobile app logs in with company-user accounts instead (Phase 4).

**Recommended stack**

| Part | Choice | Why |
|---|---|---|
| Admin web app | Next.js (App Router) + TypeScript in `admin/` | Server-side calls to the API keep the admin token in an httpOnly cookie; host on AWS Amplify or Vercel |
| Mobile app | Expo (React Native) + TypeScript in `mobile/` | One codebase, built-in audio recording |
| Password hashing | `bcrypt` via `passlib` | Admin and company-user logins (API credentials stay SHA-256, they're random) |
| Payments | Stripe, or Paystack if most customers pay in African currencies | Hosted checkout + webhooks |

Every task lists files, implementation details, tests and a commit message.

---

## Phase 0: Finish the clean-up

### ✅ T0.1 Security fixes (done, commits already suggested)
Hardcoded secrets removed, hashed API credentials and refresh tokens, token type checks, enrollment 4xx fix, S3 keys, per-company rate limiting, Alembic owns schema, test suite, UTF-8 requirements.

### T0.2 Apply the migration and scrub secrets from history (you)
- Back up the DB (`pg_dump`), set `FERNET_KEY` once, run `alembic upgrade head`.
- Add `JWT_SECRET` and `SECRET_KEY` (different random values) to the `.env` the app reads.
- Before pushing: squash or rewrite the unpushed commits `704a84c`, `8f7ba40`, `81a9219` that contain secrets, and change the Supabase DB password.
- No commit (history rewrite / ops only).

### ✅ T0.3 Deployment runs migrations (done)
- Lambda doesn't run a startup command, so add a migration step to the deploy pipeline (e.g. a CI job, or a one-off Lambda/ECS task running `alembic upgrade head`) before switching traffic.
- `Dockerfile`: delete the commented-out versions; for container deploys use `CMD alembic upgrade head && uvicorn ...` or a separate migrate job.
- Add a `README.md`: setup, `.env.example`, migrations, `scripts/manage_company.py`, running tests, API flow.
```
docs: add README and run Alembic migrations as part of deployment
```

### ✅ T0.4 CI (done)
- `.github/workflows/ci.yml`: install `requirements.txt`, run `pytest`. Tests need no secrets or models.
- `actions/checkout` with `submodules: false` (tests stub AASIST).
```
ci: run test suite on push and pull request
```

### ✅ T0.5 Logging and config clean-up (done: `MATCH_THRESHOLD` now defaults to 0.8)
- Replace the ~40 `print("[DEBUG] ...")` calls in routes with `logging`; stop logging decoded token payloads.
- Move thresholds (`MATCH_THRESHOLD`, `SIMILARITY_THRESHOLD`, `SPOOF_THRESHOLD`, `CHALLENGE_TTL`) into `Settings` so they can be tuned per environment. Review `MATCH_THRESHOLD = 0.2`: it accepts a transcript only 20% similar to the challenge, which weakens the liveness check.
- Log spoof-rejected verification attempts in `verification_logs` (currently not recorded).
- `orm_mode` → `from_attributes` in `app/schemas.py`.
- Delete dead code: `app/routes/company.py` (commented out), the commented-out block in `app/anti_spoofing/aasist.py`, `test_pipeline.py`, `app/utils/verification.py`'s unused `transcribe_audio`/`compute_embedding`.
```
refactor: structured logging, configurable thresholds and dead code removal
```

---

## Phase 1: Billing-ready core (backend)

### ✅ T1.1 Company status and multiple API keys (done: migration `c4e8a1f2b3d6`)
- `Company.status`: `pending` / `active` / `suspended` (default `active` for existing rows) and `email`.
- New `ApiCredential` table: id, company_id, name, key_prefix, key_hash (unique), secret_hash, created_at, last_used_at, revoked_at. This allows key rotation without downtime (create new → deploy → revoke old).
- Migration: copy each company's `api_key_hash` / `api_key_prefix` / `api_secret_hash` into one `ApiCredential` row named "default", then drop those columns from `companies`.
- `POST /v1/token`: look up by `ApiCredential.key_hash` where `revoked_at IS NULL`; reject `suspended` companies with 403; update `last_used_at`. Put `credential_id` into the access token for usage tracking.
- Update `scripts/manage_company.py` (`create`, `add-key`, `revoke-key`).
- Tests: revoked key 401, suspended company 403, two keys both work.
```
feat(auth): add company status and multiple revocable API credentials per company
```

### T1.2 Current-user dependency
- `get_current_user` in `app/auth.py`: verifies the token (existing `verify_token`), loads the `User` and its `Company` in one query, returns 404/403 if the user is gone or the company is suspended.
- Replace the repeated "parse UUID → query user → 404" blocks in `challenge.py`, `enrollment.py`, `verification.py`.
- Suspending a company then blocks existing access tokens immediately, not after expiry.
```
refactor(auth): add get_current_user dependency and enforce company status
```

### T1.3 Plans, subscriptions and usage tables
| Model | Key columns |
|---|---|
| `Plan` | id, name, monthly_price, currency, monthly_verifications, monthly_enrollments, is_public, is_active |
| `Subscription` | id, company_id, plan_id, status (`active`/`past_due`/`cancelled`), current_period_start, current_period_end, provider, provider_ref |
| `UsageRecord` | id, company_id, credential_id, user_id, kind (`enrollment_sample`/`verification`), status_code, created_at |

- Index `UsageRecord(company_id, created_at)`.
- Seed migration with e.g. *Free trial*, *Starter*, *Growth*, *Enterprise*.
```
feat(billing): add plan, subscription and usage record tables
```

### T1.4 Usage metering and quotas
- Dependency `enforce_quota(kind)` on `/v1/enroll-voice` and `/v1/secure-verify-voice`:
  - No active subscription → 402 `{"detail": "No active subscription"}`.
  - Successful usage this period ≥ plan limit → 429 `{"detail": "Monthly quota exceeded"}`.
- Record a `UsageRecord` for every attempt that reaches processing (after challenge checks), with the final status; only `< 400` counts toward quota.
- Headers: `X-Quota-Limit`, `X-Quota-Remaining`.
- Keep `/v1/challenge` and `/v1/token` unmetered (rate limit protects them).
- Tests: under quota, at quota 429, no subscription 402, new period resets, failed attempts don't count.
```
feat(billing): meter enrollment and verification usage and enforce plan quotas
```

---

## Phase 2: Admin API (`/admin/*`)

### T2.1 Admin accounts and login
- `AdminUser`: id (UUID), email (unique), password_hash, is_active, created_at.
- `POST /admin/auth/login` → JWT `{"sub", "type": "admin"}` signed with a new `ADMIN_JWT_SECRET`; dependency `get_current_admin`.
- `scripts/create_admin.py --email ...` (password via `getpass`).
- Router package `app/routes/admin/`, mounted at `/admin`, own rate limit for login (e.g. 5/minute per IP).
```
feat(admin): add admin users, login and bootstrap script
```

### T2.2 Company management
- `POST /admin/companies` (name, email, optional plan) → returns the first API key + secret once.
- `GET /admin/companies?status=&q=&page=` list; `GET /admin/companies/{id}` with subscription, credential list, user count, this month's usage.
- `PATCH /admin/companies/{id}`: edit, `activate`, `suspend`.
- Move create/rotate logic from `scripts/manage_company.py` into `app/services/companies.py`; the script and the API both call it.
```
feat(admin): add company onboarding and management endpoints
```

### T2.3 Plans and subscriptions
- CRUD `/admin/plans` (deactivate instead of delete).
- `POST /admin/companies/{id}/subscription` assign a plan manually (invoiced customers); `DELETE` cancels.
```
feat(admin): manage plans and assign subscriptions
```

### T2.4 Credentials
- `POST /admin/companies/{id}/credentials` (shown once), `GET` list (prefix, name, last used), `POST /admin/credentials/{id}/revoke`.
```
feat(admin): issue, list and revoke company API credentials
```

### T2.5 Stats
- `GET /admin/stats`: active companies, calls this month, verification success rate, spoof rejection rate, MRR.
- `GET /admin/companies/{id}/usage?from=&to=` daily counts by kind.
- `GET /admin/companies/{id}/verification-logs` (paged; phrase, similarity, spoof_prob, result) for support.
```
feat(admin): add platform stats, usage and verification log endpoints
```

---

## Phase 3: Admin web app (`admin/`)

### T3.1 Scaffold and login
- `npx create-next-app@latest admin --typescript --app --eslint`; one UI kit (Mantine or shadcn/ui); `@tanstack/react-query` for client-side refreshes.
- Login = a Server Action that calls `POST /admin/auth/login` and stores the admin JWT in an **httpOnly, Secure, SameSite=Strict cookie**; the browser never sees the token.
- `lib/api.ts` (server-only): reads the cookie, calls the API at `TRUEVOICE_API_URL` (a server env var, not `NEXT_PUBLIC_`), maps 401 to a redirect to `/login`.
- `middleware.ts` sends any request without the cookie to `/login`; logout deletes the cookie.
- Pages call the API from Server Components and Server Actions, so the FastAPI app needs no CORS for the admin app.
```
feat(admin-web): scaffold admin dashboard with login
```

### T3.2 Companies
- List (status filter, search), "Onboard company" form showing the key + secret once with copy buttons, detail page tabs: Overview (activate/suspend), Subscription, Credentials, Usage, Verification logs.
```
feat(admin-web): add company onboarding, detail and credential screens
```

### T3.3 Plans
```
feat(admin-web): add plan management screen
```

### T3.4 Dashboard
- Stat tiles + daily usage chart (`recharts`), spoof rejection trend.
```
feat(admin-web): add dashboard stats and usage charts
```

### T3.5 Hosting
- Next.js uses a server for login and data fetching, so a static S3 bucket isn't enough: deploy to AWS Amplify Hosting (same AWS account as the API) or Vercel, from `main`.
- Set `TRUEVOICE_API_URL` and a cookie secret as server environment variables.
```
ci(admin-web): deploy Next.js admin app on merge to main
```

---

## Phase 4: Business self-service (`/portal/*`, backend for the mobile app)

**Assumption:** the mobile app is for a business to sign up, buy a plan, manage keys and usage, and test voice verification. Their customer-facing apps integrate via their own backend.

### T4.1 Company accounts
- `CompanyMember`: id, company_id, email, password_hash, role (`owner`/`member`).
- `POST /portal/auth/signup` creates a `pending` company + owner; `POST /portal/auth/login` → JWT `{"type": "company_member", "company_id", "sub"}`; dependency `get_current_member`.
- Optional email verification.
```
feat(portal): add company self sign-up and member login
```

### T4.2 Payments
- `GET /portal/plans`; `POST /portal/checkout {plan_id}` → provider checkout URL with company/plan metadata.
- `POST /webhooks/payments`: verify signature, create/renew `Subscription`, activate company; `past_due` on failed renewal; idempotent via `PaymentEvent(provider_event_id unique)`.
- Only the webhook activates subscriptions.
- Lambda note: the webhook needs the raw request body for signature checks; test it through Mangum.
```
feat(billing): add plan checkout and payment webhook activation
```

### T4.3 Self-management
- `GET /portal/me` (company, subscription, usage vs quota), `/portal/credentials` (create/list/revoke via `app/services`), `GET /portal/usage`.
- `POST /portal/sandbox-token {user_id}` → normal access + refresh tokens for a `sandbox:`-prefixed test user, so the mobile app can call `/v1/challenge`, `/v1/enroll-voice`, `/v1/secure-verify-voice` without an API secret. Give sandbox users a small separate quota.
```
feat(portal): add company profile, credentials, usage and sandbox tokens
```

---

## Phase 5: Business mobile app (`mobile/`)

### T5.1 Scaffold
- `create-expo-app` TypeScript, `expo-router`, `@tanstack/react-query`, `expo-secure-store`, `expo-audio`; API client with `EXPO_PUBLIC_API_URL`.
```
feat(mobile): scaffold Expo app with navigation and API client
```

### T5.2 Sign-up, login and purchase
- Sign up, log in, choose plan; checkout via `expo-web-browser`; poll `/portal/me` until active.
- Check current App Store / Play rules for B2B purchases outside the app.
```
feat(mobile): add business sign-up, login and plan checkout
```

### T5.3 Dashboard, credentials and usage
- Plan + quota bar, credentials (create shows once, `expo-clipboard`), daily usage.
```
feat(mobile): add dashboard, credential management and usage screens
```

### T5.4 Voice test console
- Language picker from `GET /v1/languages`.
- Enroll: 3 rounds of `GET /v1/challenge` → record → `POST /v1/enroll-voice`, showing "sample n/3".
- Verify: challenge → record → `POST /v1/secure-verify-voice`; show verified, similarity, spoof probability.
- Refresh the access token with `/v1/token/refresh` when it expires.
- Handle mic permission, challenge expiry (120 s), 402/429 (link to plans), 403 spoof.
```
feat(mobile): add voice enroll and verify test console
```

### T5.5 Build config
- `eas.json` profiles, per-environment API URLs, `NSMicrophoneUsageDescription`.
```
chore(mobile): add EAS build profiles and app config
```

---

## Phase 6: Hardening and docs

### T6.1 Integration guide
- `docs/INTEGRATION.md`: backend token flow, refresh/revoke, challenge → enroll ×3 → verify, error codes (400, 401, 402, 403, 404, 413, 429), samples in Node, Python and cURL.
```
docs: add business integration guide
```

### T6.2 Audit log and observability
- `AuditLog` for admin and member actions (credential created/revoked, company suspended, plan changed).
- Request ID middleware, JSON logs to CloudWatch, `/health` checks DB connectivity.
```
feat: add audit log, request IDs and deeper health check
```

### T6.3 CI for all apps
- Backend `pytest`, admin `npm run build && npm run lint`, mobile `npx tsc --noEmit`.
```
ci: run backend tests and admin/mobile checks
```

---

## Suggested order
T0.2 → T0.3–T0.5 → T1.1–T1.4 → T2.1–T2.4 → T3.1–T3.2 → T4.1, T4.3 → T5.1, T5.4 → rest.

**Shortest demo path:** T0.2, T1.1, T1.2, T2.1, T2.2, T3.1, T3.2, T4.1, T4.3, T5.1, T5.4. Assign plans manually from the admin app and add quotas (T1.3–T1.4) and payments (T4.2, T5.2) after.
