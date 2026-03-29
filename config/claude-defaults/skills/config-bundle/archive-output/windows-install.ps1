# Claude Code + Hook-Flow-Bundle Installer for Windows
# Usage: irm https://raw.githubusercontent.com/.../windows-install.ps1 | iex
# Or: .\windows-install.ps1 -ApiKey "sk-ant-..."

param(
    [string]$ApiKey = $env:ANTHROPIC_API_KEY,
    [string]$BundleUrl = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=== Claude Code + Hook-Flow-Bundle Installer ===" -ForegroundColor Cyan

# 1. Install Node.js if not present
if (!(Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "[1/5] Installing Node.js..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    $env:PATH = "$env:PATH;C:\Program Files\nodejs"
} else {
    Write-Host "[1/5] Node.js already installed" -ForegroundColor Green
}

# 2. Install Claude Code CLI
Write-Host "[2/5] Installing Claude Code CLI..." -ForegroundColor Yellow
npm install -g @anthropic-ai/claude-code

# 3. Create .claude directory structure
Write-Host "[3/5] Creating .claude directory..." -ForegroundColor Yellow
$claudeDir = "$env:USERPROFILE\.claude"
$hooksDir = "$claudeDir\hooks"
$skillsDir = "$claudeDir\skills"

New-Item -ItemType Directory -Force -Path $hooksDir | Out-Null
New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null

# 4. Set API key if provided
if ($ApiKey) {
    Write-Host "[4/5] Configuring API key..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $ApiKey, "User")
    $env:ANTHROPIC_API_KEY = $ApiKey
} else {
    Write-Host "[4/5] No API key provided - set ANTHROPIC_API_KEY env var manually" -ForegroundColor Yellow
}

# 5. Download and install hook-flow-bundle
Write-Host "[5/5] Installing hook-flow-bundle..." -ForegroundColor Yellow
if ($BundleUrl) {
    # Download bundle
    $bundlePath = "$env:TEMP\hook-flow-bundle.zip"
    Invoke-WebRequest -Uri $BundleUrl -OutFile $bundlePath
    Expand-Archive -Path $bundlePath -DestinationPath "$skillsDir\hook-flow-bundle" -Force
    
    # Run installer
    Push-Location "$skillsDir\hook-flow-bundle"
    node install-workflow.js
    Pop-Location
} else {
    Write-Host "  No bundle URL provided - skipping bundle install" -ForegroundColor Yellow
    Write-Host "  To install later: node install-workflow.js <bundle.zip>" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host "Run 'claude' to start Claude Code" -ForegroundColor Cyan
Write-Host ""
