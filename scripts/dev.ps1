# Owner: Dev B. Starts the backend and frontend dev servers in two PowerShell windows.
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location -LiteralPath '$backend'; uv run uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location -LiteralPath '$frontend'; npm run dev"
