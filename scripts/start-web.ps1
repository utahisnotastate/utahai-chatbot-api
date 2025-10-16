param(
  [string]$Port = "5173"
)

# Verify Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "Node.js is required. Install from https://nodejs.org/ (v18+ recommended)." -ForegroundColor Yellow
  exit 1
}

Push-Location "$PSScriptRoot\..\web"

try {
  if (-not (Test-Path "node_modules")) {
    Write-Host "Installing web dependencies (npm install)..." -ForegroundColor Cyan
    npm install | Out-Host
  }

  $env:PORT = $Port
  Write-Host "Starting Vite dev server on port $Port..." -ForegroundColor Cyan
  npm run dev | Out-Host
}
finally {
  Pop-Location
}
