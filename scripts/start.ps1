param(
    [switch]$NoWeb,
    [switch]$NoModel
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.runtime\conda\python.exe'
$RuntimeLogs = Join-Path $ProjectRoot '.runtime\logs'
$Ollama = Join-Path $ProjectRoot '.runtime\ollama\ollama.exe'

Set-Location -LiteralPath $ProjectRoot
New-Item -ItemType Directory -Force -Path $RuntimeLogs | Out-Null
$env:PYTHONNOUSERSITE = '1'

& $Python scripts/postgres_runtime.py start
& $Python scripts/apply_migrations.py

function Test-LocalPort {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

if (-not $NoModel -and (Test-Path -LiteralPath $Ollama) -and -not (Test-LocalPort 11434)) {
    $env:OLLAMA_MODELS = Join-Path $ProjectRoot 'models\ollama'
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_NO_CLOUD = 'true'
    Start-Process -FilePath $Ollama -ArgumentList 'serve' -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RuntimeLogs 'ollama.out.log') `
        -RedirectStandardError (Join-Path $RuntimeLogs 'ollama.err.log')
}

if (-not (Test-LocalPort 8000)) {
    Start-Process -FilePath $Python `
        -ArgumentList '-m','uvicorn','apps.api.app.main:app','--host','127.0.0.1','--port','8000' `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RuntimeLogs 'api.out.log') `
        -RedirectStandardError (Join-Path $RuntimeLogs 'api.err.log')
}

if (-not $NoWeb -and -not (Test-LocalPort 5173)) {
    Start-Process -FilePath 'npm.cmd' -ArgumentList '--prefix','apps/web','run','dev','--','--host','127.0.0.1' `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RuntimeLogs 'web.out.log') `
        -RedirectStandardError (Join-Path $RuntimeLogs 'web.err.log')
}

Write-Output 'Services are starting: API http://127.0.0.1:8000, Web http://127.0.0.1:5173'
