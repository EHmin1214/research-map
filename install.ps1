# Research Map - install as a personal skill for every agent found on this machine
# (Claude Code and Codex CLI).
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Claude
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Codex
#   powershell -ExecutionPolicy Bypass -File install.ps1 -To C:\path\to\skills
#
# To install as a plugin instead, see README (plugin marketplace add).

param(
  [switch]$Claude,
  [switch]$Codex,
  [switch]$NoVSCode,
  [string]$To
)

$ErrorActionPreference = "Stop"
# The doctor output contains non-ASCII; keep consoles from mangling it.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8" } catch {}

$src = Join-Path $PSScriptRoot "skills\research-map"
if (-not (Test-Path $src)) { throw "skills\research-map not found next to this script" }

# python?
$py = $null; $v = $null
foreach ($c in @("python", "python3", "py")) {
  if (Get-Command $c -ErrorAction SilentlyContinue) {
    $v = & $c -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
  }
}
if (-not $py) { Write-Host "! Python 3.8+ not found on PATH. Install it, then re-run." -ForegroundColor Yellow }
else { Write-Host "python      $py ($v)" }

# where to install
$targets = @()
if ($To) {
  $targets += (Join-Path $To "research-map")
} else {
  $wantClaude = -not $Codex
  $wantCodex  = -not $Claude
  $claudeHome = Join-Path $env:USERPROFILE ".claude"
  $codexHome  = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
  if ($wantClaude -and (Test-Path $claudeHome)) { $targets += (Join-Path $claudeHome "skills\research-map") }
  if ($wantCodex  -and (Test-Path $codexHome))  { $targets += (Join-Path $codexHome  "skills\research-map") }
}

if ($targets.Count -eq 0) {
  Write-Host "! No agent home found (~/.claude or ~/.codex)." -ForegroundColor Yellow
  Write-Host "  Install one, or pass -To <skills-directory>."
  exit 1
}

foreach ($dst in $targets) {
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  # Clear old contents without deleting the folder itself: a terminal sitting in it,
  # or a stale __pycache__, must not break the install.
  $stuck = 0
  Get-ChildItem -Recurse -Force $dst | Sort-Object FullName -Descending | ForEach-Object {
    try { Remove-Item -Force -Recurse -LiteralPath $_.FullName -ErrorAction Stop } catch { $stuck++ }
  }
  Copy-Item -Recurse -Force (Join-Path $src "*") $dst
  Write-Host "installed   $dst" -ForegroundColor Green
  if ($stuck -gt 0) { Write-Host "note        $stuck old item(s) were locked and left in place" -ForegroundColor DarkGray }
}

if ($py) {
  Write-Host ""
  & $py (Join-Path $targets[0] "scripts\extract.py") --doctor
}

# VS Code / Cursor status-bar button (three files, no download). Skip with -NoVSCode.
if (-not $NoVSCode -and -not $To) {
  $ext = Join-Path $PSScriptRoot "vscode\research-map"
  if (Test-Path $ext) {
    $ides = @()
    foreach ($ide in @(".vscode", ".cursor")) {
      $d = Join-Path $env:USERPROFILE "$ide\extensions"
      if (Test-Path $d) { $ides += (Join-Path $d "local.research-map-0.1.0") }
    }
    foreach ($root in $ides) {
      New-Item -ItemType Directory -Force -Path $root | Out-Null
      foreach ($f in @("package.json", "extension.js", "README.md")) {
        Copy-Item -Force (Join-Path $ext $f) (Join-Path $root $f)
      }
      Write-Host "installed   $root  (status-bar button; reload the window once)" -ForegroundColor Green
    }
  }
}
Write-Host ""
Write-Host "Next: ask your agent  'build my research map'"
