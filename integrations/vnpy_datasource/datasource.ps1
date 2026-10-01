param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
$ErrorActionPreference = 'Stop'
$runtimePolicy = Get-Content -LiteralPath 'D:\repo\quant\runtime-policy.json' -Raw | ConvertFrom-Json
$researchPython = $runtimePolicy.projects.vnpy.python
if (-not (Test-Path -LiteralPath $researchPython)) { throw 'Unified research Python was not found. See D:\repo\quant\RUNTIMES.md.' }
if (-not $Arguments) { $Arguments = @('--help') }
Push-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))
try {
    & $researchPython -X utf8 -m vnpy_datasource.cli @Arguments
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
