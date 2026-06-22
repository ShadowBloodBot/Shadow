# Restore Cursor + Shadow local access after machine wipe.
# Interactive:  cd C:\Users\JOEPC\OneDrive\Desktop\JoePower\projects\Shadow; .\scripts\setup_cursor_access.ps1
# Non-interactive: fill .local-secrets.env then:
#   .\scripts\setup_cursor_access.ps1 -SecretsFile .local-secrets.env

param(
    [string]$SecretsFile = ""
)

$ErrorActionPreference = "Stop"
$ShadowRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$CursorMcp = Join-Path $ShadowRoot ".cursor\mcp.json"
$EnvRailway = Join-Path $ShadowRoot ".env.railway"
$GlobalMcp = Join-Path $env:USERPROFILE ".cursor\mcp.json"

$ShadowMainGuild = "908659586536468540"
$RailwayProjectId = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
$RailwayService = "Shadow"

function Read-Secret([string]$Prompt) {
    $sec = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Load-SecretsFile([string]$Path) {
    if (-not (Test-Path $Path)) { throw "Secrets file not found: $Path" }
    $map = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        if ($line -match '^([^=]+)=(.*)$') { $map[$Matches[1].Trim()] = $Matches[2].Trim() }
    }
    return $map
}

Write-Host ""
Write-Host "=== Shadow / Cursor access restore ===" -ForegroundColor Cyan

if ($SecretsFile) {
    $resolved = if ([System.IO.Path]::IsPathRooted($SecretsFile)) { $SecretsFile } else { Join-Path $ShadowRoot $SecretsFile }
    $secrets = Load-SecretsFile $resolved
    $adminToken = $secrets["SHADOWADMIN_DISCORD_TOKEN"]
    $railwayToken = $secrets["RAILWAY_API_TOKEN"]
    $githubToken = $secrets["GITHUB_PERSONAL_ACCESS_TOKEN"]
} else {
    Write-Host "Get tokens from:"
    Write-Host "  ShadowAdmin bot: https://discord.com/developers/applications/1513810670569656390/bot"
    Write-Host "  Railway API:     https://railway.com/account/tokens"
    Write-Host "  GitHub PAT:      https://github.com/settings/tokens (repo scope for ShadowBloodBot/Shadow)"
    Write-Host ""
    $adminToken = Read-Secret "ShadowAdmin DISCORD_TOKEN (Bot tab - Reset Token - copy)"
    $railwayToken = Read-Secret "RAILWAY_API_TOKEN"
    $githubToken = Read-Secret "GitHub personal access token (ghp_...)"
}

if (-not $adminToken -or -not $railwayToken -or -not $githubToken) {
    Write-Error "All three tokens are required."
}

New-Item -ItemType Directory -Path (Split-Path $CursorMcp) -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path $GlobalMcp) -Force | Out-Null

$projectMcp = @{
    mcpServers = @{
        "discord-admin" = @{
            command = "npx"
            args    = @("-y", "@quadslab.io/discord-mcp")
            env     = @{
                DISCORD_TOKEN    = $adminToken
                DISCORD_GUILD_ID = $ShadowMainGuild
            }
        }
    }
} | ConvertTo-Json -Depth 6
$projectMcp | Set-Content -Path $CursorMcp -Encoding UTF8
Write-Host "Wrote $CursorMcp" -ForegroundColor Green

@"
RAILWAY_API_TOKEN=$railwayToken
RAILWAY_PROJECT_ID=$RailwayProjectId
RAILWAY_SERVICE=$RailwayService
"@ | Set-Content -Path $EnvRailway -Encoding UTF8 -NoNewline
Add-Content -Path $EnvRailway -Value ""
Write-Host "Wrote $EnvRailway" -ForegroundColor Green

$globalMcpObj = @{
    mcpServers = @{
        "discord-admin" = @{
            command = "npx"
            args    = @("-y", "@quadslab.io/discord-mcp")
            env     = @{
                DISCORD_TOKEN    = $adminToken
                DISCORD_GUILD_ID = $ShadowMainGuild
            }
        }
        github = @{
            command = "npx"
            args    = @("-y", "@modelcontextprotocol/server-github")
            env     = @{
                GITHUB_PERSONAL_ACCESS_TOKEN = $githubToken
            }
        }
    }
}
if (Test-Path $GlobalMcp) {
    try {
        $existing = Get-Content $GlobalMcp -Raw | ConvertFrom-Json
        foreach ($prop in $existing.mcpServers.PSObject.Properties) {
            if (-not $globalMcpObj.mcpServers.ContainsKey($prop.Name)) {
                $globalMcpObj.mcpServers[$prop.Name] = $prop.Value
            }
        }
    } catch {
        Write-Warning "Could not merge existing global mcp.json; overwriting."
    }
}
($globalMcpObj | ConvertTo-Json -Depth 6) | Set-Content -Path $GlobalMcp -Encoding UTF8
Write-Host "Wrote $GlobalMcp" -ForegroundColor Green

# GitHub CLI auth (non-interactive)
$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
    $githubToken | gh auth login --with-token 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "gh auth: OK" -ForegroundColor Green }
    else { Write-Warning "gh auth login failed - run: gh auth login" }
} else {
    Write-Warning "gh not on PATH yet. Restart terminal, then: gh auth login"
}

# Quick validation
Write-Host ""
Write-Host "=== Validation ===" -ForegroundColor Cyan

try {
    $headers = @{ Authorization = "Bot $adminToken" }
    $me = Invoke-RestMethod -Uri "https://discord.com/api/v10/users/@me" -Headers $headers
    Write-Host "Discord ShadowAdmin: $($me.username) (app 1513810670569656390)" -ForegroundColor Green
} catch {
    Write-Warning "Discord token check failed: $_"
}

try {
    $body = '{"query":"{ projects { edges { node { id name } } } }"}'
    $rw = Invoke-RestMethod -Uri "https://backboard.railway.app/graphql/v2" -Method Post `
        -Headers @{ Authorization = "Bearer $railwayToken"; "Content-Type" = "application/json"; "User-Agent" = "ShadowSyn/1.0" } `
        -Body $body
    if ($rw.data.projects) { Write-Host "Railway API: OK ($($rw.data.projects.edges.Count) project(s))" -ForegroundColor Green }
    else { Write-Warning "Railway response unexpected" }
} catch {
    Write-Warning "Railway token check failed: $_"
}

if ($gh) {
    gh auth status 2>&1 | ForEach-Object { Write-Host $_ }
}

Write-Host ""
Write-Host "Done. Reload Cursor (Ctrl+Shift+P -> Developer: Reload Window)." -ForegroundColor Cyan
Write-Host "Open workspace: C:\Users\JOEPC\OneDrive\Desktop\JoePower\projects\Shadow" -ForegroundColor Cyan
Write-Host "ShadowSyn production token stays on Railway - deploy scripts fetch DISCORD_TOKEN from there." -ForegroundColor DarkGray
