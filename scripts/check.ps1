# One-shot quality gate: lint (autofix), format, re-lint, test.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

ruff check --fix yesir tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ruff format yesir tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ruff check yesir tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest -q
exit $LASTEXITCODE
