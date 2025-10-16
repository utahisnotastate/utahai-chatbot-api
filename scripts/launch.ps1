param(
  [string]$ProjectId = "utahai",
  [string]$Location = "global",
  [string]$DataStoreId = "utahai-knowledge-base",
  [string]$BackendPort = "8080",
  [string]$WebPort = "5173",
  [switch]$NoBrowser
)

Write-Host "=== UtahAI: Launching local chat stack (API + Web UI) ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectId | Location: $Location | DataStore: $DataStoreId" -ForegroundColor DarkCyan

# --- Verify Python ---
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python is required. Install Python 3.11+ from https://www.python.org/downloads/" -ForegroundColor Yellow
  exit 1
}

# --- Verify Node.js ---
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "Node.js is required. Install from https://nodejs.org/ (v18+ recommended)." -ForegroundColor Yellow
  exit 1
}

# Go to repo root (one level up from scripts folder)
$repoRoot = Join-Path $PSScriptRoot ".."

# Install Python deps if needed
Push-Location $repoRoot
try {
  Write-Host "Ensuring Python dependencies are installed (pip install -r requirements.txt)..." -ForegroundColor Cyan
  python -m pip install --upgrade pip | Out-Host
  python -m pip install --no-cache-dir -r requirements.txt | Out-Host
}
finally {
  Pop-Location
}

# Start backend in a new PowerShell window
$backendCmd = @"
`$env:PROJECT_ID='$ProjectId'; `$env:LOCATION='$Location'; `$env:DATA_STORE_ID='$DataStoreId'; `$env:PORT='$BackendPort';
Write-Host 'Starting backend (Flask) on port $BackendPort...' -ForegroundColor Cyan
python main.py
"@

Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-NoLogo", "-Command", $backendCmd) -WorkingDirectory $repoRoot | Out-Null

# Start web UI in a new PowerShell window
$webDir = Join-Path $repoRoot "web"
$webCmd = @"
if (-not (Test-Path 'node_modules')) { Write-Host 'Installing web dependencies (npm install)...' -ForegroundColor Cyan; npm install | Out-Host }
`$env:PORT='$WebPort'; `$env:VITE_API_URL='http://localhost:$BackendPort';
Write-Host 'Starting Web UI (Vite) on port $WebPort...' -ForegroundColor Cyan
npm run dev
"@
Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-NoLogo", "-Command", $webCmd) -WorkingDirectory $webDir | Out-Null

# Open browser to the Web UI
if (-not $NoBrowser) {
  Start-Sleep -Seconds 2
  Start-Process "http://localhost:$WebPort" | Out-Null
}

Write-Host "Both windows should be open: API on :$BackendPort and Web UI on :$WebPort" -ForegroundColor Green
Write-Host "Tip: Run GET http://localhost:$BackendPort/setup/check to verify Discovery Engine connectivity." -ForegroundColor DarkGreen
