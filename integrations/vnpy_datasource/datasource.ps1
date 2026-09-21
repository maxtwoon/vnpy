param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
$ErrorActionPreference = 'Stop'
$studioPython = 'D:\veighna_studio\python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Studio Python was not found.' }
if (-not $Arguments) { $Arguments = @('--help') }
Push-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))
try {
    & $studioPython -X utf8 -m vnpy_datasource.cli @Arguments
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
