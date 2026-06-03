# Porta de verificacio local (Windows / PowerShell).
# Executa la mateixa bateria que la CI: backend pytest + frontend type-check/lint/build.
# Us: pwsh scripts/verifica.ps1   (o:  pwsh scripts/verifica.ps1 -Skip build)
param(
    [string[]]$Skip = @()  # p. ex. -Skip build  per saltar el build del frontend
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Step($nom, $accio) {
    if ($Skip -contains $nom) { Write-Host "== $nom (omes) ==" -ForegroundColor DarkGray; return }
    Write-Host "== $nom ==" -ForegroundColor Cyan
    & $accio
    if ($LASTEXITCODE -ne 0) { throw "Ha fallat: $nom" }
}

# Backend: tests (usa el venv si existeix).
Step 'backend-pytest' {
    Push-Location "$root\backend"
    try {
        $py = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
        & $py -m pytest -q
    } finally { Pop-Location }
}

# Frontend: type-check + lint + build.
Step 'frontend-type-check' { Push-Location "$root\frontend"; try { npm run type-check } finally { Pop-Location } }
Step 'frontend-lint'       { Push-Location "$root\frontend"; try { npm run lint }       finally { Pop-Location } }
Step 'build'               { Push-Location "$root\frontend"; try { npm run build }      finally { Pop-Location } }

Write-Host "`nOK - porta de verificacio verda." -ForegroundColor Green
