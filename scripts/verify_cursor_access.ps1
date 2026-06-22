# Verify local Shadow access without printing secrets.
$ShadowRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ok = $true

function Fail($msg) { Write-Host "FAIL  $msg" -ForegroundColor Red; $script:ok = $false }
function Pass($msg) { Write-Host "OK    $msg" -ForegroundColor Green }

Write-Host "=== Shadow access check ===" -ForegroundColor Cyan

$mcpPath = Join-Path $ShadowRoot ".cursor\mcp.json"
$envPath = Join-Path $ShadowRoot ".env.railway"
$globalMcp = Join-Path $env:USERPROFILE ".cursor\mcp.json"

foreach ($p in @($mcpPath, $envPath, $globalMcp)) {
    if (Test-Path $p) { Pass (Split-Path $p -Leaf) } else { Fail "Missing $p" }
}

foreach ($cmd in @("git", "gh", "node", "npx", "python")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { Pass $cmd } else { Fail "$cmd not on PATH (restart terminal after install)" }
}

if (Test-Path $mcpPath) {
    try {
        $mcp = Get-Content $mcpPath -Raw | ConvertFrom-Json
        $token = $mcp.mcpServers."discord-admin".env.DISCORD_TOKEN
        if (-not $token -or $token -match "PASTE_") { Fail "discord-admin token not set in .cursor/mcp.json" }
        else {
            $me = Invoke-RestMethod -Uri "https://discord.com/api/v10/users/@me" -Headers @{ Authorization = "Bot $token" }
            Pass "Discord ShadowAdmin: $($me.username)"
        }
    } catch { Fail "Discord: $_" }
}

if (Test-Path $envPath) {
    $railwayToken = $null
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^RAILWAY_API_TOKEN=(.+)$') { $railwayToken = $Matches[1].Trim() }
    }
    if (-not $railwayToken) { Fail "RAILWAY_API_TOKEN empty in .env.railway" }
    else {
        try {
            $body = '{"query":"query { me { name } }"}'
            $rw = Invoke-RestMethod -Uri "https://backboard.railway.com/graphql/v2" -Method Post `
                -Headers @{ Authorization = "Bearer $railwayToken"; "Content-Type" = "application/json"; "User-Agent" = "ShadowSyn/1.0" } -Body $body
            Pass "Railway: $($rw.data.me.name)"
        } catch { Fail "Railway: $_" }
    }
}

if (Get-Command gh -ErrorAction SilentlyContinue) {
    $ghOut = gh auth status 2>&1 | Out-String
    if ($ghOut -match 'Logged in to github\.com') { Pass "GitHub CLI authenticated" } else { Fail "gh not logged in - run: gh auth login -w" }
}

if ($ok) { Write-Host "`nAll checks passed." -ForegroundColor Green; exit 0 }
else { Write-Host "`nSome checks failed. Run: .\scripts\setup_cursor_access.ps1" -ForegroundColor Yellow; exit 1 }
