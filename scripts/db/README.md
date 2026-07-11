# Database Backup And Restore

These scripts are the env-specific rollback helpers for local, dev, and prod.
They read database settings from `.env.local`, `.env.dev`, or `.env.prod`.

## Requirements

- `mysqldump` and `mysql` must be installed on the machine running the script.
- The target `.env.<env>` file must contain `DB_HOST`, `DB_PORT`, `DB_USER`,
  `DB_PASSWORD`, and `DB_NAME`.
- For SSL databases, use either `DB_SSL_CA` for a cert file path or
  `DB_SSL_CA_PEM` for the PEM content/base64 value.

## Backup

PowerShell:

```powershell
.\scripts\db\backup.ps1 -Env dev
.\scripts\db\backup.ps1 -Env prod
```

Shell:

```sh
sh scripts/db/backup.sh dev
sh scripts/db/backup.sh prod
```

Backups are written to `backups/db/` by default.

## Restore

PowerShell:

```powershell
.\scripts\db\restore.ps1 -Env dev -File .\backups\db\dev-cabbo_dev-YYYYMMDD-HHMMSS.sql
.\scripts\db\restore.ps1 -Env prod -File .\backups\db\prod-cabbo_prod-YYYYMMDD-HHMMSS.sql
```

Shell:

```sh
sh scripts/db/restore.sh dev backups/db/dev-cabbo_dev-YYYYMMDD-HHMMSS.sql
sh scripts/db/restore.sh prod backups/db/prod-cabbo_prod-YYYYMMDD-HHMMSS.sql
```

Restore asks for `RESTORE` confirmation by default. Use `-Yes` in PowerShell
or `--yes` in shell only for automation.

## Rollback Flow

1. Take a backup before migrations or risky production changes.
2. Run the migration/deploy.
3. If rollback is needed, restore the most recent known-good backup.

