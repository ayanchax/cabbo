# Cabbo Backend

FastAPI backend for Cabbo, covering customer booking flows, admin operations,
payments, refunds, legal content, OTP auth, and operational configuration.

Dev API:

```text
https://api.dev.cabbo.co.in
```

## Stack

- FastAPI
- SQLAlchemy / MySQL
- Alembic
- uv
- Razorpay
- Twilio
- Sentry
- Docker / Railway

## Local Setup

```powershell
uv venv
.\.venv\Scripts\activate
uv sync
```

Create the required `.env.local` file before running the app.

## Run Locally

From the project root:

```powershell
cd src
uvicorn app:app --reload
```

Health check:

```text
GET http://localhost:8000/health
```

API docs:

```text
http://localhost:8000/docs
```

## Docker

Local:

```sh
docker compose -f docker-compose.local.yml up --build
```

Dev/prod images are built from their respective Dockerfiles. Runtime env vars
are provided by the deployment platform.

## Database Operations

Database backup, restore, migration, and seed scripts live in `scripts/db`.
They are intended to be run from a local or trusted operator machine, not from
inside the deployed API container.

Examples:

```sh
sh scripts/db/backup.sh dev
sh scripts/db/migration.sh dev
sh scripts/db/seed.sh dev
sh scripts/db/restore.sh dev backups/db/<backup-file>.sql
```

See `scripts/db/README.md` for the recommended flow.

## Legal Content

Legal/support pages are stored as Markdown under `content/legal` and exposed
through read-only legal page APIs for frontend consumption.

## Notes

- Do not commit `.env.*`, database dumps, PEM files, or local backups.
- Deployed logs go to stdout/stderr; local logs may use the local log folder.
- Sentry is enabled for non-local environments when configured.

