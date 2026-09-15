@echo off
rem Research Map - open a map with the update buttons enabled.
rem
rem Starts the local server (127.0.0.1 only) and opens the page in your browser.
rem Close this window, or press Ctrl+C, to stop it.
rem You can still double-click maps\<name>\index.html for a plain read-only view.
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

rem --- python?
set "PY="
for %%C in (python py python3) do (
  if not defined PY (
    %%C -c "import sys;assert sys.version_info>=(3,8)" >nul 2>&1 && set "PY=%%C"
  )
)
if not defined PY (
  echo Python 3.8+ not found on PATH.
  pause
  exit /b 1
)

rem --- where did the skill get installed?
for /f "usebackq delims=" %%D in (`%PY% -c "import glob,os;H=os.path.expanduser;c=[H('~/.claude/skills/research-map/scripts'),H('~/.codex/skills/research-map/scripts')]+sorted(glob.glob(H('~/.claude/plugins/cache/*/research-map/*/skills/research-map/scripts')))+sorted(glob.glob(H('~/.codex/plugins/cache/*/research-map/*/skills/research-map/scripts')));h=[q for q in c if os.path.isdir(q)];print(h[0] if h else '')"`) do set "RM=%%D"

if not defined RM (
  echo research-map skill not found. Falling back to the static page.
  for /d %%M in ("%~dp0maps\*") do if exist "%%~fM\index.html" start "" "%%~fM\index.html"
  exit /b 0
)

rem --- which map? one map needs no argument
set "MAPARG="
if not "%~1"=="" set "MAPARG=--map %~1"

echo Starting the research map server...
%PY% "%RM%\render.py" %MAPARG% --serve
endlocal
