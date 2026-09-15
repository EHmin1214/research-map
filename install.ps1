# Research Map - install as a personal Claude Code skill (Windows / PowerShell)
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Copies skills/research-map into ~/.claude/skills/ so Claude Code picks it up.
# If you would rather install it as a plugin, see README (plugin marketplace add).

$ErrorActionPreference = "Stop"
# The doctor output and the closing hint contain non-ASCII; keep consoles from mangling them.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8" } catch {}
$src = Join-Path $PSScriptRoot "skills\research-map"
$dst = Join-Path $env:USERPROFILE ".claude\skills\research-map"

if (-not (Test-Path $src)) { throw "skills\research-map not found next to this script" }

# python?
$py = $null
foreach ($c in @("python", "python3", "py")) {
  $cmd = Get-Command $c -ErrorAction SilentlyContinue
  if ($cmd) {
    $v = & $c -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
  }
}
if (-not $py) { Write-Host "! Python 3.8+ not found on PATH. Install it, then re-run." -ForegroundColor Yellow }
else { Write-Host "python      $py ($v)" }

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

if ($py) {
  Write-Host ""
  & $py (Join-Path $dst "scripts\extract.py") --doctor
}
Write-Host ""
Write-Host "Next: open Claude Code and say  'build my research map'  (Korean: research map + 'make'/'update')"
