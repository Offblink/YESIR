# One-shot quality gate: lint (autofix), format, re-lint, test.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

ruff check --fix oksir tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ruff format oksir tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ruff check oksir tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest -q
exit $LASTEXITCODE
