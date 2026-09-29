$ErrorActionPreference = 'Stop'
$executable = Join-Path $PSScriptRoot 'release\FinancialAssistant.exe'
if (-not (Test-Path -LiteralPath $executable)) {
    throw 'Executable not found. Build it once with: .\scripts\build.ps1'
}
& $executable
exit $LASTEXITCODE
