<#
.SYNOPSIS
    Backup and restore Claude Code configuration
.USAGE
    .\backup.ps1              # Create timestamped backup
    .\backup.ps1 restore      # Restore latest backup
    .\backup.ps1 restore <name>  # Restore specific backup
    .\backup.ps1 list         # List available backups
#>

param([string]$action = "backup", [string]$target = "")

$claudeDir = "$env:USERPROFILE\.claude"
$backupDir = "$claudeDir\backups"

$items = @("settings.json", "CLAUDE.md", "hooks", "skills")

switch ($action) {
    "backup" {
        $name = Get-Date -Format "yyyy-MM-dd_HHmmss"
        $dest = "$backupDir\$name"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null

        foreach ($item in $items) {
            $src = "$claudeDir\$item"
            if (Test-Path $src) {
                Copy-Item -Path $src -Destination "$dest\$item" -Recurse -Force
            }
        }
        Write-Host "Created: $name"

        # Keep last 10
        Get-ChildItem $backupDir -Directory | Sort-Object Name -Descending |
            Select-Object -Skip 10 | Remove-Item -Recurse -Force
    }
    "restore" {
        $src = if ($target) { "$backupDir\$target" }
               else { (Get-ChildItem $backupDir -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName }

        if (-not (Test-Path $src)) { Write-Host "Backup not found"; exit 1 }

        foreach ($item in $items) {
            if (Test-Path "$src\$item") {
                Copy-Item -Path "$src\$item" -Destination "$claudeDir\$item" -Recurse -Force
            }
        }
        Write-Host "Restored from: $(Split-Path $src -Leaf)"
        Write-Host "Restart Claude Code to apply."
    }
    "list" {
        Get-ChildItem $backupDir -Directory | Sort-Object Name -Descending | ForEach-Object { $_.Name }
    }
}
