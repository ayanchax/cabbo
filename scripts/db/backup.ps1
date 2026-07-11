param(
    [ValidateSet("local", "dev", "prod")]
    [string]$Env = "local",
    [string]$OutDir = "backups/db"
)

$ErrorActionPreference = "Stop"

function Read-DotEnvValue {
    param([string]$Path, [string]$Key)

    $line = Get-Content -Path $Path | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -Last 1
    if (-not $line) {
        return $null
    }

    $value = $line -replace "^\s*$Key\s*=", ""
    return $value.Trim().Trim("'").Trim('"')
}

function Resolve-CaFile {
    param([string]$EnvFile)

    $caPath = Read-DotEnvValue -Path $EnvFile -Key "DB_SSL_CA"
    if ($caPath) {
        if ([IO.Path]::IsPathRooted($caPath)) {
            return $caPath
        }
        return (Join-Path (Get-Location) $caPath)
    }

    $caPem = Read-DotEnvValue -Path $EnvFile -Key "DB_SSL_CA_PEM"
    if ($caPem) {
        $tempCa = Join-Path ([IO.Path]::GetTempPath()) "cabbo-db-ca-$Env.pem"
        if ($caPem -notmatch "-----BEGIN CERTIFICATE-----") {
            $bytes = [Convert]::FromBase64String($caPem)
            [IO.File]::WriteAllBytes($tempCa, $bytes)
        }
        else {
            $caPem = $caPem.Replace("\n", "`n")
            Set-Content -Path $tempCa -Value $caPem -NoNewline
        }
        return $tempCa
    }

    return $null
}

$envFile = ".env.$Env"
if (-not (Test-Path $envFile)) {
    throw "Environment file not found: $envFile"
}

$dbHost = Read-DotEnvValue -Path $envFile -Key "DB_HOST"
$dbPort = Read-DotEnvValue -Path $envFile -Key "DB_PORT"
$dbUser = Read-DotEnvValue -Path $envFile -Key "DB_USER"
$dbPassword = Read-DotEnvValue -Path $envFile -Key "DB_PASSWORD"
$dbName = Read-DotEnvValue -Path $envFile -Key "DB_NAME"
$caFile = Resolve-CaFile -EnvFile $envFile

if (-not $dbHost -or -not $dbPort -or -not $dbUser -or -not $dbPassword -or -not $dbName) {
    throw "Missing one or more DB_* values in $envFile"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = Join-Path $OutDir "$Env-$dbName-$timestamp.sql"

$previousMysqlPwd = $env:MYSQL_PWD
$env:MYSQL_PWD = $dbPassword

try {
    $args = @(
        "--host=$dbHost",
        "--port=$dbPort",
        "--user=$dbUser",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF"
    )

    if ($caFile) {
        $args += "--ssl-ca=$caFile"
        $args += "--ssl-mode=VERIFY_IDENTITY"
    }

    $args += $dbName

    Write-Host "Creating $Env DB backup at $backupFile"
    & mysqldump @args | Set-Content -Path $backupFile -Encoding UTF8

    if ($LASTEXITCODE -ne 0) {
        throw "mysqldump failed with exit code $LASTEXITCODE"
    }

    Write-Host "Backup complete: $backupFile"
}
finally {
    if ($null -eq $previousMysqlPwd) {
        Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
    }
    else {
        $env:MYSQL_PWD = $previousMysqlPwd
    }
}
