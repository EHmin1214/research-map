# Research Map — VS Code status-bar button

A tiny local extension that puts **연구 지도** in the VS Code status bar. Clicking it gives a
menu:

| Item | What runs |
|---|---|
| 열기 — 갱신·정정 버튼 켜서 | `render.py --map <name> --serve` in a terminal named `연구 지도: <name>` (the page opens in your browser; the terminal keeps the local server alive) |
| 읽기 전용으로 열기 | opens `maps/<name>/index.html` directly |
| 새 세션 확인 | `extract.py --map <name>` — free |
| 지도 갱신 (에이전트) | `rmserve.py --map <name> --update` — extract, then the agent CLI writes cards, merges and renders. Spends tokens, so it asks first |
| 논문용 내보내기 | `rmexport.py --map <name> [--checklist]` |
| 새 지도 만들기 | `extract.py --init <name> --title <title>` |

With one map the menu skips the map picker. The scripts are found the same way
`open-map.bat` finds them (personal skill dirs, then plugin caches); set
`researchMap.scripts` if you installed the skill somewhere else. `researchMap.home` overrides
`~/.claude/research-map`, `researchMap.python` picks the interpreter.

## Install

```powershell
.\install.ps1        # copies into ~/.vscode/extensions (and ~/.cursor/extensions if present)
```

Then reload the VS Code window once. Nothing is downloaded; the extension is three files.

## 한국어

상태바 왼쪽 아래 **연구 지도** 를 누르면 열기 / 새 세션 확인 / 갱신 / 내보내기 / 새 지도 메뉴가
뜬다. 실제 실행은 전부 스킬의 Python 스크립트이고 이 확장은 터미널에서 그걸 불러 줄 뿐이다.
갱신은 토큰을 쓰므로 한 번 확인창이 뜬다. 설치는 `install.ps1` 한 번, 그 뒤 VS Code 창 다시 로드.
