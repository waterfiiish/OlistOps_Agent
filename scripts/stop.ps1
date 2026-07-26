$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.runtime\conda\python.exe'

$listeners = Get-NetTCPConnection -State Listen -LocalPort 8000,5173,11434 -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $pathMatches = $process -and $process.Path -and `
        $process.Path.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)
    $commandMatches = $processInfo -and $processInfo.CommandLine -and `
        ($processInfo.CommandLine.IndexOf(
            $ProjectRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0)
    if ($process -and ($pathMatches -or $commandMatches)) {
        Stop-Process -Id $process.Id -Force
    }
}

if (Test-Path -LiteralPath $Python) {
    & $Python scripts/postgres_runtime.py stop
}

Write-Output 'Stopped OlistOps project-local services.'
