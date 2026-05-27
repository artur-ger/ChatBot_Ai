param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$AdminToken = "",
    [string]$AdminUsername = "",
    [string]$AdminPassword = ""
)

$ErrorActionPreference = "Stop"

function Get-AdminSession {
    if (-not $AdminUsername -or -not $AdminPassword) {
        return $null
    }
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $loginBody = (@{ username = $AdminUsername; password = $AdminPassword } | ConvertTo-Json -Compress)
    $login = Invoke-WebRequest -Uri "$BaseUrl/api/v1/admin/login" -Method Post `
        -ContentType "application/json" -Body $loginBody -WebSession $session -UseBasicParsing
    if ($login.StatusCode -ne 200) {
        throw "admin login failed: $($login.StatusCode)"
    }
    return $session
}

Write-Host "Smoke test: $BaseUrl"

for ($i = 1; $i -le 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "$BaseUrl/healthz" -Method Get -TimeoutSec 5
        if ($health.status -eq "ok") { break }
    } catch {
        if ($i -eq 30) { throw "healthz failed after retries: $($_.Exception.Message)" }
        Start-Sleep -Seconds 2
    }
}
Write-Host "[OK] healthz"

$ready = Invoke-RestMethod -Uri "$BaseUrl/readyz" -Method Get
if ($ready.status -ne "ready") {
    throw "readyz failed: $($ready | ConvertTo-Json -Compress)"
}
Write-Host "[OK] readyz"

$ui = Invoke-RestMethod -Uri "$BaseUrl/system/ui-config" -Method Get
Write-Host "[OK] ui-config show_admin_link=$($ui.show_admin_link) chat_acl_required=$($ui.chat_acl_required)"

$info = Invoke-RestMethod -Uri "$BaseUrl/system/info" -Method Get
Write-Host "[OK] system/info llm_configured=$($info.llm_configured) integrations=$($info.llm_integrations_count) active=$($info.active_llm_provider)/$($info.active_llm_model)"
if ($info.active_llm_provider -eq "rule_based") {
    throw "активна rule_based"
}

$chatBody = @{
    chat_id = "smoke-user"
    text    = "ping smoke test"
} | ConvertTo-Json -Compress

$chat = Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json" -Body $chatBody
if (-not $chat.text) {
    throw "chat response missing text"
}
Write-Host "[OK] chat text length=$($chat.text.Length) sources=$($chat.sources.Count)"

try {
    Invoke-RestMethod -Uri "$BaseUrl/api/v1/documents" -Method Post | Out-Null
    throw "expected 401 for unauthenticated document upload"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 401) {
        throw "expected 401 for unauthenticated document upload, got $($_.Exception.Response.StatusCode.value__)"
    }
}
Write-Host "[OK] documents API requires admin auth"

$session = Get-AdminSession
if ($session) {
    $prompt = Invoke-RestMethod -Uri "$BaseUrl/api/v1/admin/rag/prompt" -Method Get -WebSession $session
    if (-not $prompt.system_instruction) {
        throw "rag prompt missing system_instruction"
    }
    Write-Host "[OK] admin cookie login + rag prompt"

    $docsUri = '{0}/api/v1/documents?status=indexed&limit=5' -f $BaseUrl
    $docs = Invoke-RestMethod -Uri $docsUri -WebSession $session
    Write-Host "[OK] admin cookie documents indexed count=$($docs.items.Count)"
}

if ($AdminToken) {
    $headers = @{ Authorization = "Bearer $AdminToken" }

    $prompt = Invoke-RestMethod -Uri "$BaseUrl/api/v1/admin/rag/prompt" -Method Get -Headers $headers
    if (-not $prompt.system_instruction) {
        throw "rag prompt missing system_instruction"
    }
    Write-Host "[OK] admin token rag prompt"

    $llmList = Invoke-RestMethod -Uri "$BaseUrl/api/v1/admin/llm/integrations" -Method Get -Headers $headers
    Write-Host "[OK] admin token llm list count=$($llmList.items.Count)"
}

if (-not $session -and -not $AdminToken) {
    Write-Host "[SKIP] admin checks (pass -AdminToken or -AdminUsername/-AdminPassword)"
}

Write-Host "Smoke test passed."
