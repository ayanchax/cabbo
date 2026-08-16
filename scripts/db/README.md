# Database Operations

These scripts are env-specific database helpers for local, dev, and prod.
They read database settings from `.env.local`, `.env.dev`, or `.env.prod`.

Run everything in this folder from your local machine or trusted operator
machine. This includes backup, restore, migration, and seed. These scripts are
not meant to run inside the deployed API container. The environment argument
selects which `.env.<env>` file is loaded, so the same local script can connect
to the local, dev, or prod database remotely.

Examples:

```sh
sh scripts/db/backup.sh dev
sh scripts/db/migration.sh prod
sh scripts/db/seed.sh local
sh scripts/db/bulk_onboard_system_users.sh local
sh scripts/db/bulk_onboard_drivers.sh local
sh scripts/db/restore.sh dev backups/db/dev-cabbo_dev-YYYYMMDD-HHMMSS.sql
```

Treat `prod` commands as production operations. Take a backup before migrations,
one-off seed changes, restore testing, or any risky data operation.

## Requirements

- `mysqldump` and `mysql` must be installed on the machine running the script.
- Python dependencies for the backend must be installed when running migrations
  or seed scripts.
- The target `.env.<env>` file must contain `DB_HOST`, `DB_PORT`, `DB_USER`,
  `DB_PASSWORD`, and `DB_NAME`.
- For SSL databases, use either `DB_SSL_CA` for a cert file path or
  `DB_SSL_CA_PEM` for the PEM content/base64 value.

## Backup

```sh
sh scripts/db/backup.sh dev
sh scripts/db/backup.sh prod
```

Backups are written to `backups/db/` by default.

## Migration

Run Alembic migrations against the selected environment:

```sh
sh scripts/db/migration.sh local
sh scripts/db/migration.sh dev
sh scripts/db/migration.sh prod
```

## Seed

Run one-off seed data against the selected environment:

```sh
sh scripts/db/seed.sh local
sh scripts/db/seed.sh dev
sh scripts/db/seed.sh prod
```

## Bulk System User Onboarding

Use this only for the curated v1 system-user onboarding batch when admin users
need to be created operationally outside the normal recurring seed flow. The
script reads `scripts/data/v1_system_users.yaml`, validates rows through
`UserCreateSchema` and `validate_system_user_payloads`, and calls the bulk user
creation service.

This is intentionally separate from `seed.py`. Seed data should be repeatable
system/master data, while this batch is operational access data for real admin
users, phone numbers, usernames, and roles. It should be run deliberately by an
operator, not replayed automatically as part of normal environment bootstrap.

Dry-run first:

```sh
sh scripts/db/bulk_onboard_system_users.sh local
sh scripts/db/bulk_onboard_system_users.sh dev
```

Insert after reviewing the dry-run output:

```sh
sh scripts/db/bulk_onboard_system_users.sh local --execute
sh scripts/db/bulk_onboard_system_users.sh dev --execute
```

Use a custom YAML file if needed:

```sh
sh scripts/db/bulk_onboard_system_users.sh local --file scripts/data/v1_system_users.yaml --execute
```

Do not run this as a normal recurring seed. Database uniqueness constraints on
system-user usernames, emails, and phone numbers are the source of truth for
duplicate protection; duplicate rows will fail through the normal service/DB
exception path which is expected.

## Bulk Driver Onboarding

Use this only for the curated v1 driver onboarding batch when the admin console
does not yet expose driver CRUD. The script reads `scripts/data/v1_drivers.yaml`,
validates the rows through `DriverCreateSchema`, and calls the bulk driver
creation service.

This is intentionally separate from `seed.py`. Seed data should be repeatable
system/master data, while this batch is operational onboarding data for real
drivers, phone numbers, and cab registrations. It should be run deliberately by
an operator, not replayed automatically as part of normal environment bootstrap.

Dry-run first:

```sh
sh scripts/db/bulk_onboard_drivers.sh local
sh scripts/db/bulk_onboard_drivers.sh dev
```

Insert after reviewing the dry-run output:

```sh
sh scripts/db/bulk_onboard_drivers.sh local --execute
sh scripts/db/bulk_onboard_drivers.sh dev --execute
```

Use a custom YAML file if needed:

```sh
sh scripts/db/bulk_onboard_drivers.sh local --file scripts/data/v1_drivers.yaml --execute
```

Do not run this as a normal recurring seed. Database uniqueness constraints on
driver phone, secondary phone, and cab registration are the source of truth for
duplicate protection; duplicate rows will fail through the normal service/DB
exception path which is expected.

## Restore

```sh
sh scripts/db/restore.sh dev backups/db/dev-cabbo_dev-YYYYMMDD-HHMMSS.sql
sh scripts/db/restore.sh prod backups/db/prod-cabbo_prod-YYYYMMDD-HHMMSS.sql
```

Restore asks for `RESTORE` confirmation by default. Use `--yes` in shell only for automation.

## Recommended Flow

For local/dev migration testing:

1. Run `sh scripts/db/backup.sh dev`.
2. Run `sh scripts/db/migration.sh dev`.
3. Run `sh scripts/db/seed.sh dev` only if the migration needs new seed data.
4. Run `sh scripts/db/bulk_onboard_system_users.sh dev --execute` only for the
   v1 system-user onboarding batch after a dry-run review.
5. Run `sh scripts/db/bulk_onboard_drivers.sh dev --execute` only for the v1
   driver onboarding batch after a dry-run review.
6. Smoke test the app against dev.
7. If needed, run `sh scripts/db/restore.sh dev <backup-file>`.

For prod:

1. Confirm the dev migration and seed path is already tested.
2. Run `sh scripts/db/backup.sh prod`.
3. Run `sh scripts/db/migration.sh prod`.
4. Run `sh scripts/db/seed.sh prod` only if required.
5. Run `sh scripts/db/bulk_onboard_system_users.sh prod --execute` only if the
   v1 system-user onboarding batch has already been tested in dev and reviewed.
6. Run `sh scripts/db/bulk_onboard_drivers.sh prod --execute` only if the v1
   driver onboarding batch has already been tested in dev and reviewed.
7. Smoke test the production app.
8. If rollback is needed, run `sh scripts/db/restore.sh prod <backup-file>`.

For restore testing:

1. Prefer testing restore on local or dev first.
2. Take a fresh backup before restore testing.
3. Restore the selected backup.
4. Verify important tables and app startup after restore.

## Rollback Flow

1. Take a backup before migrations or risky production changes.
2. Run the migration/deploy.
3. Run seed only when required for that environment.
4. If rollback is needed, restore the most recent known-good backup.
