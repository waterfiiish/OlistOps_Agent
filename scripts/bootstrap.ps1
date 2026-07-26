param(
    [switch]$SkipData,
    [switch]$SkipOllama
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CondaPrefix = Join-Path $ProjectRoot '.runtime\conda'
$Python = Join-Path $CondaPrefix 'python.exe'

Set-Location -LiteralPath $ProjectRoot
$env:PYTHONNOUSERSITE = '1'

if (-not (Test-Path -LiteralPath $Python)) {
    conda create --prefix $CondaPrefix --override-channels -c conda-forge `
        python=3.12 postgresql=16 pgvector=0.8.3 pip -y
}

& $Python -m pip install -e '.[dev]'
npm install
& $Python scripts/postgres_runtime.py start
& $Python scripts/apply_migrations.py

if (-not $SkipData) {
    & $Python scripts/download_olist.py
    & $Python scripts/load_data.py
    & $Python scripts/data_quality_report.py
    & $Python scripts/build_knowledge.py
}

if (-not $SkipOllama) {
    & $Python scripts/install_ollama.py
}

Write-Output 'Bootstrap complete. Run scripts/start.ps1 to launch local services.'
