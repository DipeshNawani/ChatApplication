$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Create .venv and install server/requirements.txt first; see README.md.'
}
& $pythonExecutable (Join-Path $projectDirectory 'server\run.py')
if ($LASTEXITCODE -ne 0) {
    throw "The chat backend exited with code $LASTEXITCODE. Check the error above."
}
