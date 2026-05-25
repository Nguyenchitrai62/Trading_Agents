param(
    [string]$EnvPath = (Join-Path $PSScriptRoot ".env"),
    [string]$OutputPath = (Join-Path $PSScriptRoot "FE/runtime-config.js")
)

if (-not (Test-Path $EnvPath)) {
    throw "Missing .env file at $EnvPath"
}

$backendMatch = Select-String -Path $EnvPath -Pattern '^\s*BACKEND_BASE_URL\s*=\s*(.+?)\s*$' | Select-Object -First 1
if (-not $backendMatch) {
    throw "BACKEND_BASE_URL is missing from $EnvPath"
}

$backendBaseUrl = $backendMatch.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
if (-not $backendBaseUrl) {
    throw "BACKEND_BASE_URL is empty in $EnvPath"
}

$backendBaseUrl = $backendBaseUrl.TrimEnd('/')

$runtimeConfig = @"
window.TRADINGAGENTS_RUNTIME_CONFIG = {
    // Generated from .env so static FE and Live Server share the same backend URL.
    apiBaseUrl: "$backendBaseUrl",
};
"@

Set-Content -Path $OutputPath -Value $runtimeConfig -Encoding utf8
Write-Output "Synced FE/runtime-config.js from BACKEND_BASE_URL=$backendBaseUrl"