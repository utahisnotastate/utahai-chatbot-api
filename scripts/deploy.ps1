param(
  [string]$ProjectId = "utahai",
  [string]$Region = "us-central1",
  [string]$Service = "utahai-chatbot-api",
  [string]$Location = "global",
  [string]$DataStoreId = "utahai-knowledge-base"
)

# Determine project root directory (parent of the script's directory)
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Write-Host "Project root identified as: $ProjectRoot" -ForegroundColor Cyan

Write-Host "Setting gcloud project to $ProjectId" -ForegroundColor Cyan
& gcloud config set project $ProjectId | Out-Host

Write-Host "Enabling required APIs (may take a minute)..." -ForegroundColor Cyan
& gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com discoveryengine.googleapis.com | Out-Host

Write-Host "Deploying Cloud Run service '$Service' in $Region from source: $ProjectRoot" -ForegroundColor Cyan
& gcloud run deploy $Service `
  --source $ProjectRoot `
  --platform managed `
  --region $Region `
  --allow-unauthenticated `
  --set-env-vars "PROJECT_ID=$ProjectId,LOCATION=$Location,DATA_STORE_ID=$DataStoreId" | Out-Host

# Retrieve and print the service URL
$serviceUrl = ""
try {
  $serviceUrl = & gcloud run services describe $Service --region $Region --format "value(status.url)"
} catch {}

if ($serviceUrl) {
  Write-Host "Deploy succeeded. Service URL: $serviceUrl" -ForegroundColor Green
  Write-Host "Quick checks:" -ForegroundColor DarkGreen
  Write-Host "  GET $serviceUrl/ (should show status: ok and effective data store ID)" -ForegroundColor DarkGreen
  Write-Host "  GET $serviceUrl/setup/check (should show status: ok)" -ForegroundColor DarkGreen
  Write-Host "Test chat:" -ForegroundColor DarkGreen
  Write-Host "  ./scripts/test-chat.ps1 -Url $serviceUrl -Query 'Hello'" -ForegroundColor DarkGreen
  Write-Host "Next: Build and deploy the Web UI pointing to this API:" -ForegroundColor DarkGreen
  Write-Host "  ./scripts/deploy-web.ps1 -Bucket <YOUR_STATIC_BUCKET> -ApiUrl $serviceUrl" -ForegroundColor DarkGreen
} else {
  Write-Host "If deploy succeeded, your service URL is shown above. You can test with scripts/test-chat.ps1 -Url <SERVICE_URL>" -ForegroundColor Green
}
