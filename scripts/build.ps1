$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    & $python -B scripts/check.py --scope all
    if ($LASTEXITCODE -ne 0) { throw 'Checks failed; release was not changed.' }
    New-Item -ItemType Directory -Path "$projectRoot\build" -Force | Out-Null
    $buildLog = Join-Path $projectRoot 'build\packaging.log'
    & $python -m PyInstaller --noconfirm --onefile --console --name FinancialAssistant `
        --distpath build/staging --workpath build/pyinstaller --specpath build `
        --add-data "${projectRoot}\static:static" --collect-submodules uvicorn --copy-metadata jdatetime `
        --exclude-module httpx --exclude-module httpx2 --exclude-module pytest `
        launcher.py *> $buildLog
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $buildLog -Tail 40
        throw "Packaging failed; see $buildLog"
    }
    $candidate = Join-Path $projectRoot 'build\staging\FinancialAssistant.exe'
    & $candidate --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Executable self-test failed; release was not changed.' }
    New-Item -ItemType Directory -Path "$projectRoot\release" -Force | Out-Null
    Copy-Item -LiteralPath $candidate -Destination "$projectRoot\release\FinancialAssistant.exe" -Force
    Write-Output 'Ready: release\FinancialAssistant.exe'
} finally {
    Pop-Location
}
