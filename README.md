# TrueVoice API

Voice biometric verification for businesses. A company integrates the API from its own backend; its end users enroll their voice once, then verify by speaking a one-time challenge phrase.

Each verification checks three things:
- **Liveness:** the user says the random challenge phrase (OpenAI Whisper transcription)
- **Anti-spoofing:** the audio isn't synthetic or replayed (AASIST)
- **Identity:** the voice matches the enrolled voiceprint (SpeechBrain ECAPA-TDNN)

## API flow

All routes except `/health` are under `/v1`. Interactive docs: `/docs`.

```
Business backend                         TrueVoice
  POST /v1/token  (X-API-KEY, X-API-SECRET, {"user_id": "<your user id>", "lang": "en"})
                                         → access_token, refresh_token
Business app (with the user's access token)
  GET  /v1/challenge                     → {"challenge_text": "three eight one five six"}
  POST /v1/enroll-voice   (audio)        → "sample 1/3 saved"   ┐ repeat challenge + enroll
                                                                ┘ 3 times
  GET  /v1/challenge
  POST /v1/secure-verify-voice (audio)   → {"verified": true, "similarity": ..., "spoof_prob": ...}
```

- A challenge is valid for 120 seconds and can be used once.
- Access tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`; get a new one with `POST /v1/token/refresh`. Revoke a refresh token with `POST /v1/token/revoke`.
- `GET /v1/languages` lists supported languages.
- The API key and secret must stay on the business's server. Never ship them in a mobile or web app.

## Local setup

Requires Python 3.13, PostgreSQL and ffmpeg.

```bash
python -m venv venvTruevoice
venvTruevoice\Scripts\activate          # Windows
source venvTruevoice/bin/activate       # macOS / Linux
pip install -r requirements.txt
git submodule update --init app/third_party/aasist
```

### Configuration

Copy `.env.example` to `.env` and fill it in. Every secret is required; the app refuses to start without them.

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | PostgreSQL connection |
| `JWT_SECRET` | Signs access tokens |
| `SECRET_KEY` | Signs refresh tokens (use a different value from `JWT_SECRET`) |
| `ADMIN_JWT_SECRET` | Signs admin dashboard tokens (a third, different value) |
| `ADMIN_TOKEN_EXPIRE_MINUTES`, `ADMIN_LOGIN_RATE_LIMIT` | Admin session length (default `480`) and login attempts per IP (default `5/minute`) |
| `RATE_LIMIT` | Requests per company (or per IP without a token), e.g. `60/minute` |
| `LOG_LEVEL` | `DEBUG`, `INFO` (default), `WARNING` or `ERROR` |
| `CHALLENGE_TTL` | Seconds a challenge phrase stays valid (default `120`) |
| `MATCH_THRESHOLD` | Minimum transcript/challenge text similarity, 0–1 (default `0.8`) |
| `SPOOF_THRESHOLD` | Maximum AASIST spoof probability accepted, 0–1 (default `0.30`) |
| `SIMILARITY_THRESHOLD` | Minimum voiceprint cosine similarity for a match (default `0.65`) |
| `OPENAI_API_KEY` | Whisper transcription and challenge generation |
| `AWS_*`, `S3_BUCKET_NAME` | Audio storage |

Generate secrets with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Database

The schema is managed by Alembic. The app does not create tables on startup.

```bash
alembic upgrade head
```

After changing `app/models.py`, create a migration and review it before committing:
```bash
alembic revision --autogenerate -m "describe the change"
```

### Companies

Companies are created from the command line for now (an admin app is on the [roadmap](docs/ROADMAP.md)):

```bash
python -m scripts.manage_company create "Acme Bank" --email ops@acme.com
python -m scripts.manage_company add-key "Acme Bank" --key-name production
python -m scripts.manage_company list-keys "Acme Bank"
python -m scripts.manage_company revoke-key <credential id from list-keys>
python -m scripts.manage_company rotate "Acme Bank"     # emergency: revoke every key, issue one new key
python -m scripts.manage_company suspend "Acme Bank"    # or: activate
```

API keys and secrets are printed once. Only their hashes are stored, so they can't be shown again; if they're lost, add a new key and revoke the old one.

A company can hold several keys. To rotate without downtime: `add-key`, deploy the new key, then `revoke-key` the old one. Revoking a key also stops refresh tokens issued with it. Only `active` companies get tokens; `pending` and `suspended` ones get 403.

### Admins

Admins sign in to the admin API (`/admin/*`) and, later, the admin dashboard. Create the first one from the command line; the password is asked for at a hidden prompt (at least 12 characters):

```bash
python -m scripts.create_admin --email you@example.com
python -m scripts.create_admin --email you@example.com --reset-password
python -m scripts.create_admin --email you@example.com --deactivate      # or --activate
```

`POST /admin/auth/login` with `{"email", "password"}` returns an admin token; send it as `Authorization: Bearer <token>`. `GET /admin/auth/me` returns the signed-in admin. Admin tokens and end-user tokens use different secrets, so neither works on the other's routes.

| Admin endpoint | Purpose |
|---|---|
| `POST /admin/companies` | Onboard a company (`name`, optional `email`, `status`); returns its first API key and secret once |
| `GET /admin/companies?status=&q=&page=&page_size=` | List and search companies, with user and active-key counts |
| `GET /admin/companies/{id}` | Company detail: API keys (prefixes only), user count, this month's verifications and enrollments |
| `PATCH /admin/companies/{id}` | Edit `name` / `email`, or set `status` to `active`, `suspended` or `pending` (takes effect immediately) |
| `POST /admin/companies/{id}/credentials` | Issue another API key (optional `name`, e.g. for rotation); returns the key and secret once |
| `GET /admin/companies/{id}/credentials?include_revoked=` | The company's API keys, newest first: name, prefix, created, last used, revoked |
| `POST /admin/credentials/{id}/revoke` | Revoke a key; it and tokens already issued with it stop working at once |

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pytest
```

The tests mock OpenAI, S3, the voice models and the database (in-memory SQLite), so they need no `.env`, network access or model weights.

## Deployment

**Docker:** the image runs `alembic upgrade head` before starting the API. If migrations run as a separate deploy step, set `RUN_MIGRATIONS=0`.

```bash
docker build -t truevoice .
docker run --env-file .env -p 8000:8000 truevoice
```

**AWS Lambda:** `app.main.handler` is the Mangum entry point. Lambda has no startup command, so run `alembic upgrade head` against the production database from your deploy pipeline before releasing a new version.

## Project layout

```
app/
  main.py            FastAPI app, routers, rate limiter, Lambda handler
  config.py          Settings from environment / .env
  auth.py            Access token creation and validation
  rate_limit.py      Per-company rate limiting
  models.py          SQLAlchemy models
  routes/            token, challenge, enrollment, verification, languages, health
  utils/             audio processing, S3 storage, OpenAI client, credential hashing
  anti_spoofing/     AASIST spoof detection
alembic/             Database migrations
scripts/             Command-line tools (company management)
tests/               Pytest suite
docs/ROADMAP.md      Planned work: admin app, subscriptions, mobile app
```
