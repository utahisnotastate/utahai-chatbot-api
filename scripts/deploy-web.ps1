param(
  [Parameter(Mandatory=$true)][string]$Bucket,
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [string]$WebsiteMain = "index.html",
  [string]$Region = "US",
  [switch]$NoPublic
)

Write-Host "=== UtahAI: Deploying Web UI to Google Cloud Storage ===" -ForegroundColor Cyan
Write-Host "Bucket: gs://$Bucket | API URL: $ApiUrl" -ForegroundColor DarkCyan

# --- Verify tooling ---
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "Node.js is required. Install from https://nodejs.org/ (v18+ recommended)." -ForegroundColor Yellow
  exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Host "npm is required. It ships with Node.js. Install from https://nodejs.org/." -ForegroundColor Yellow
  exit 1
}
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  Write-Host "gcloud CLI is required. Install from https://cloud.google.com/sdk" -ForegroundColor Yellow
  exit 1
}
if (-not (Get-Command gsutil -ErrorAction SilentlyContinue)) {
  Write-Host "gsutil is required (installed with gcloud)." -ForegroundColor Yellow
  exit 1
}

# --- Build the web app ---
$webDir = Join-Path $PSScriptRoot "..\web"
Push-Location $webDir
try {
  if (-not (Test-Path "node_modules")) {
    Write-Host "Installing web dependencies (npm install)..." -ForegroundColor Cyan
    npm install | Out-Host
  }
  $env:VITE_API_URL = $ApiUrl
  Write-Host "Building production bundle (VITE_API_URL=$ApiUrl)..." -ForegroundColor Cyan
  npm run build | Out-Host
}
finally {
  Pop-Location
}

# --- Ensure bucket exists ---
$bucketUri = "gs://$Bucket"
$bucketExists = $true
try {
  & gsutil ls -b $bucketUri | Out-Null
} catch {
  $bucketExists = $false
}

if (-not $bucketExists) {
  Write-Host "Creating bucket $bucketUri in region $Region..." -ForegroundColor Cyan
  & gsutil mb -l $Region -b on $bucketUri | Out-Host
}

# --- Optional: make public for easy testing ---
if (-not $NoPublic) {
  Write-Host "Making bucket objects publicly readable (allUsers:objectViewer)..." -ForegroundColor Cyan
  & gsutil iam ch allUsers:objectViewer $bucketUri | Out-Host
}

# --- Set website config (main page) ---
Write-Host "Setting website config (main page: $WebsiteMain)..." -ForegroundColor Cyan
& gsutil web set -m $WebsiteMain $bucketUri | Out-Host

# --- Upload files ---
$distDir = Join-Path $webDir "dist"
if (-not (Test-Path $distDir)) {
  Write-Host "Build output not found at $distDir. Aborting." -ForegroundColor Red
  exit 1
}

Write-Host "Uploading $distDir to $bucketUri ..." -ForegroundColor Cyan
& gsutil -m rsync -r -d $distDir $bucketUri | Out-Host

# --- Output final URLs ---
$websiteUrl = "https://storage.googleapis.com/$Bucket/$WebsiteMain"
Write-Host "Deployment complete." -ForegroundColor Green
Write-Host "Open: $websiteUrl" -ForegroundColor Green
Write-Host "Note: If you use a custom domain or CDN, point it at this bucket." -ForegroundColor DarkGreen
