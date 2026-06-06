# Backup operatiu d'una instancia Adeptify.
# Crea un dump Postgres i una copia tar de /app/data del backend, sense egress.
#
# Us:
#   pwsh scripts/backup.ps1
#   pwsh scripts/backup.ps1 -OutputDir C:\backups\adeptify-core -Database corerag -PostgresUser corerag
param(
    [string]$OutputDir = "",
    [string]$Database = "corerag",
    [string]$PostgresUser = "corerag",
    [string[]]$ComposeFiles = @("docker-compose.yml")
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $root "backups"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$outAbs = (Resolve-Path $OutputDir).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

function ComposeArgs {
    $args = @()
    foreach ($file in $ComposeFiles) {
        $path = Join-Path $root $file
        if (Test-Path $path) {
            $args += @("-f", $path)
        }
    }
    return $args
}

function RunCompose([string[]]$ArgsToRun) {
    $compose = ComposeArgs
    $args = $compose + $ArgsToRun
    & docker compose @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose ha fallat: $($ArgsToRun -join ' ')"
    }
}

$compose = ComposeArgs
$dbContainer = (& docker compose @compose ps -q db).Trim()
if (-not $dbContainer) {
    throw "No s'ha trobat el contenidor 'db'. Arrenca l'stack abans de fer backup."
}

$dbTmp = "/tmp/adeptify-db-$stamp.dump"
$dbOut = Join-Path $outAbs "db_$stamp.dump"
RunCompose @("exec", "-T", "db", "pg_dump", "-U", $PostgresUser, "-d", $Database, "-Fc", "-f", $dbTmp)
& docker cp "${dbContainer}:$dbTmp" $dbOut
if ($LASTEXITCODE -ne 0) { throw "No s'ha pogut copiar el dump de BD." }
RunCompose @("exec", "-T", "db", "rm", "-f", $dbTmp)

$backendOut = $null
$backendContainer = (& docker compose @compose ps -q backend).Trim()
if ($backendContainer) {
    $dataTmp = "/tmp/adeptify-backend-data-$stamp.tgz"
    $backendOut = Join-Path $outAbs "backend_data_$stamp.tgz"
    RunCompose @("exec", "-T", "backend", "sh", "-lc", "cd /app/data && tar czf $dataTmp .")
    & docker cp "${backendContainer}:$dataTmp" $backendOut
    if ($LASTEXITCODE -ne 0) { throw "No s'ha pogut copiar /app/data." }
    RunCompose @("exec", "-T", "backend", "rm", "-f", $dataTmp)
}

$manifest = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    database = $Database
    postgres_user = $PostgresUser
    db_dump = (Split-Path -Leaf $dbOut)
    backend_data = if ($backendOut) { Split-Path -Leaf $backendOut } else { $null }
    restore_note = "Restaurar nomes amb aprovacio humana, prova previa i stack aturat."
}
$manifestPath = Join-Path $outAbs "manifest_$stamp.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $manifestPath

Write-Host "Backup creat:" -ForegroundColor Green
Write-Host "  BD:       $dbOut"
if ($backendOut) { Write-Host "  /app/data: $backendOut" }
Write-Host "  Manifest: $manifestPath"
