param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$AdminToken = "",
    [string]$AdminUsername = "",
    [string]$AdminPassword = ""
)

$ErrorActionPreference = "Continue"
$failures = 0

function Get-AdminHeaders {
    if ($AdminToken) {
        return @{ Authorization = "Bearer $AdminToken" }
    }
    if ($AdminUsername -and $AdminPassword) {
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $loginBody = (@{ username = $AdminUsername; password = $AdminPassword } | ConvertTo-Json -Compress)
        $null = Invoke-WebRequest -Uri "$BaseUrl/api/v1/admin/login" -Method Post `
            -ContentType "application/json" -Body $loginBody -WebSession $session -UseBasicParsing
        return @{ WebSession = $session }
    }
    return $null
}

function Check {
    param([string]$Name, [scriptblock]$Action)
    try {
        & $Action
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] $Name - $($_.Exception.Message)" -ForegroundColor Red
        $script:failures++
    }
}

Check "healthz" {
    $r = Invoke-RestMethod -Uri "$BaseUrl/healthz"
    if ($r.status -ne "ok") { throw "not ok" }
}

Check "readyz" {
    $r = Invoke-RestMethod -Uri "$BaseUrl/readyz"
    if ($r.status -ne "ready") { throw "not ready" }
}

Check "LLM configured" {
    $r = Invoke-RestMethod -Uri "$BaseUrl/system/info"
    if (-not $r.llm_configured) { throw "llm_configured=false" }
    if ($r.active_llm_integration_id) {
        Write-Host "       active: $($r.active_llm_provider) / $($r.active_llm_model)"
    } elseif ($r.llm_using_fallback) {
        Write-Host "       warning: using rule_based fallback - add openai_compatible in /admin"
    }
}

Check "active LLM integration" {
    $r = Invoke-RestMethod -Uri "$BaseUrl/system/info"
    if (-not $r.active_llm_integration_id) {
        throw "no active LLM integration"
    }
    if ($r.active_llm_provider -eq "rule_based") {
        throw "активна rule_based; активируйте LLM в /admin"
    }
    Write-Host "       active: $($r.active_llm_provider) / $($r.active_llm_model)"
}

Check "KB index in sync" {
    $r = Invoke-RestMethod -Uri "$BaseUrl/system/kb-index"
    if ($r.state -eq "stale") {
        throw "Postgres indexed=$($r.indexed_documents) but Chroma chunks=$($r.chroma_chunks). Run reindex in /admin"
    }
    if ($r.state -eq "empty") {
        throw "KB empty: $($r.message)"
    }
    Write-Host "       indexed=$($r.indexed_documents) chroma_chunks=$($r.chroma_chunks)"
}

Check "indexed documents exist" {
    $auth = Get-AdminHeaders
    if (-not $auth) { throw "pass -AdminToken or -AdminUsername/-AdminPassword" }
    $uri = '{0}/api/v1/documents?status=indexed&limit=1' -f $BaseUrl
    if ($auth.WebSession) {
        $r = Invoke-RestMethod -Uri $uri -WebSession $auth.WebSession
    } else {
        $r = Invoke-RestMethod -Uri $uri -Headers $auth
    }
    if ($r.items.Count -lt 1) { throw "no indexed documents - upload KB in /admin" }
    Write-Host "       sample: $($r.items[0].document_id)"
}

Check "chat responds" {
    $body = '{"chat_id":"go-live","text":"test"}'
    $r = Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json" -Body $body
    if (-not $r.text) { throw "empty answer" }
}

Check "FAQ restore access sources" {
    $body = [Convert]::FromBase64String("eyJjaGF0X2lkIjogImdvLWxpdmUtZmFxIiwgInRleHQiOiAi0LrQsNC6INCy0L7RgdGB0YLQsNC90L7QstC40YLRjCDQtNC+0YHRgtGD0L8/In0=")
    $r = Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $body
    $ids = @($r.sources | ForEach-Object { $_.doc_id })
    if ($ids -notcontains "instructions.access_to_personal_account") {
        throw "expected instructions.access_to_personal_account in sources, got: $($ids -join ', ')"
    }
    Write-Host "       sources: $($ids -join ', ')"
}

Check "FAQ topup account sources" {
    $body = [Convert]::FromBase64String("eyJjaGF0X2lkIjogImdvLWxpdmUtZmFxIiwgInRleHQiOiAi0LrQsNC6INC/0L7Qv9C+0LvQvdC40YLRjCDRgdGH0LXRgj8ifQ==")
    $r = Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $body
    $ids = @($r.sources | ForEach-Object { $_.doc_id })
    if ($ids -notcontains "instructions.account") {
        throw "expected instructions.account in sources, got: $($ids -join ', ')"
    }
    Write-Host "       sources: $($ids -join ', ')"
}

Check "public UI hides admin link" {
    $ui = Invoke-RestMethod -Uri "$BaseUrl/system/ui-config"
    if ($ui.show_admin_link) {
        throw "show_admin_link=true - set PUBLIC_SHOW_ADMIN_LINK=false for prod"
    }
}

Check "admin UI reachable" {
    $r = Invoke-WebRequest -Uri "$BaseUrl/admin" -UseBasicParsing
    if ($r.StatusCode -ne 200) { throw "admin page status $($r.StatusCode)" }
    if ($r.Content -notmatch "adminUsernameInput") { throw "admin login form missing" }
}

Check "upload API protected" {
    try {
        Invoke-RestMethod -Uri "$BaseUrl/api/v1/documents" -Method Post | Out-Null
        throw "expected 401 without auth"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -ne 401) { throw "expected 401, got $code" }
    }
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "Go-live checklist: ALL PASSED" -ForegroundColor Green
    exit 0
}
Write-Host "Go-live checklist: $failures FAILED" -ForegroundColor Red
exit 1
