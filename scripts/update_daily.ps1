$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = "C:\Users\19029\anaconda3\python.exe"
$logRoot = Join-Path $projectRoot "logs"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Configured Python executable does not exist: $pythonPath"
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logRoot "tushare-update-$timestamp.log"

Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m src.update *>&1 | Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) {
        throw "Tushare update exited with code $LASTEXITCODE. See $logPath"
    }
}
finally {
    Pop-Location
}
