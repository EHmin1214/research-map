# Installs the Research Map status-bar extension into VS Code (and Cursor, if present).
# Pure ASCII on purpose: this file is read by Windows PowerShell 5.1 with the system code page.
[CmdletBinding()]
param()
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$targets = @()
foreach ($ide in @('.vscode', '.cursor')) {
    $extDir = Join-Path $env:USERPROFILE "$ide\extensions"
    if (Test-Path $extDir) { $targets += (Join-Path $extDir 'local.research-map-0.1.0') }
}
if (-not $targets) { $targets = @((Join-Path $env:USERPROFILE '.vscode\extensions\local.research-map-0.1.0')) }

foreach ($root in $targets) {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    foreach ($f in @('package.json', 'extension.js', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $f) -Destination (Join-Path $root $f) -Force
    }
    Write-Host "Installed: $root" -ForegroundColor Green
}
Write-Host 'Reload the VS Code window once (Ctrl+Shift+P > Developer: Reload Window).' -ForegroundColor Cyan
Write-Host 'Then click the "Research map" item in the status bar (bottom left).' -ForegroundColor Cyan
