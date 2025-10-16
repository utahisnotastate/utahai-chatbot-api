param(
  [Parameter(Mandatory=$true)][string]$Url,
  [string]$Query = "What documents do we have?",
  [string]$SessionId = "local-test"
)

if (-not $Url) {
  Write-Host "Usage: ./scripts/test-chat.ps1 -Url https://utahai-chatbot-api-861355800489.us-central1.run.app
 -Query 'your question'" -ForegroundColor Yellow
  exit 1
}

$body = @{ query = $Query; session_id = $SessionId } | ConvertTo-Json

Write-Host "POST $Url/chat" -ForegroundColor Cyan
$response = Invoke-RestMethod -Method Post -Uri "$Url/chat" -ContentType "application/json" -Body $body

$response | ConvertTo-Json -Depth 6 | Write-Output
