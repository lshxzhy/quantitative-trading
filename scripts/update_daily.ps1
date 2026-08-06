$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = "C:\Users\19029\anaconda3\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Configured Python executable does not exist: $pythonPath"
}

Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m src.update
    $updateExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $updateExitCode
