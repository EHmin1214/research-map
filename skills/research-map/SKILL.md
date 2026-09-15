---
name: research-map
description: 연구 지도 — 지금까지 LLM 과 진행한 연구 세션(Claude Code·Codex·다른 LLM 내보내기)을 훑어 "주제 → 방향 → 과정 → 결과 → 열린 질문" 트리로 도식화하고, 클릭하면 근거·수치·원본 세션·문서로 바로 가는 인터랙티브 HTML 마인드맵을 만든다/갱신한다. 사용자가 "연구 지도", "research map", "내가 뭘 했었지", "연구 흐름 정리", "지도 업데이트", "새 지도 만들어" 라고 하면 이 스킬을 쓴다.
---

# research-map

연구자가 LLM 과 연구를 하다 보면 자기가 어떤 갈래를 파고 어떤 결론을 냈는지 놓친다.
이 스킬은 세션 기록·메모리·문서를 **한 장의 지도**로 만든다. 노드를 클릭하면 요약·근거 수치·
더 파볼 것·원본 세션(`claude --resume` / `codex resume`)·문서 링크가 나온다.

**지도는 연구 영역마다 하나씩** 만든다. 서로 다른 과제를 한 지도에 섞지 않는다.

## 파일

| 경로 | 역할 |
|---|---|
| `scripts/rmlib.py` | 지도 관리 + **소스 어댑터**(claude-code · codex · markdown) |
| `scripts/extract.py` | 대화 기록 → 세션별 digest(md) + `sessions.json`. 증분 |
| `scripts/render.py` | `map.json` 검증 + `index.html` 생성 (단일 파일, 외부 의존 없음) |
| `scripts/rmhistory.py` | 렌더할 때마다 지도가 뭐가 움직였는지 자동 기록 (손으로 적을 필요 없음) |
| `scripts/rmserve.py` | `--serve` 로컬 서버 — 페이지의 갱신 버튼이 여기로 붙는다 |
| `MAP_SCHEMA.md` | 지도 노드 스키마 · 작성 규칙 (**갱신 전에 반드시 읽는다**) |
| `CARD_SCHEMA.md` | 세션 카드 스키마 (서브에이전트가 digest 를 읽고 쓰는 중간 산출물) |
| `<지도 폴더>` | `config.json` · `map.json` · `sessions.json` · `state.json` · `cards/` · `digests/` · `history/` · `index.html` |

## 스크립트 경로 먼저 확정 (설치 방식마다 다름)

스크립트는 **이 SKILL.md 옆 `scripts/`** 에 있다. 절대 위치는 어떻게 설치했는지에 따라 다르다.

| 설치 | 위치 |
|---|---|
| Claude Code 개인 스킬 | `~/.claude/skills/research-map/scripts/` |
| Claude Code 플러그인 | `~/.claude/plugins/cache/*/research-map/*/skills/research-map/scripts/` |
| Codex 스킬 | `~/.codex/skills/research-map/scripts/` |
| Codex 플러그인 | `~/.codex/plugins/cache/*/research-map/*/skills/research-map/scripts/` |

**1순위 — 지금 읽고 있는 이 SKILL.md 옆의 `scripts/`.** 그 경로를 안다면 그걸 쓴다.
같은 컴퓨터에 여러 벌이 설치돼 있을 수 있으므로 *다른* 사본을 부르면 버전이 갈린다.

**2순위 — 자기 경로를 모르겠으면** 세션에서 한 번 아래를 돌려 `$RM` 을 확정한다.
절대 경로를 추측하지 마라 — 없는 경로를 부르면 "스크립트가 패키지에 없다"로 오진하게 된다.

```
python -c "import glob,os;H=os.path.expanduser;cx=[H('~/.codex/skills/research-map/scripts')]+sorted(glob.glob(H('~/.codex/plugins/cache/*/research-map/*/skills/research-map/scripts')));cl=[H('~/.claude/skills/research-map/scripts')]+sorted(glob.glob(H('~/.claude/plugins/cache/*/research-map/*/skills/research-map/scripts')));c=cx+cl if os.environ.get('CODEX_HOME') or os.path.isdir(H('~/.codex/skills/research-map')) and not os.path.isdir(H('~/.claude/skills/research-map')) else cl+cx;h=[q for q in c if os.path.isdir(q)];print(h[0] if h else 'NOT FOUND')"
```

아래 명령의 `$RM` 은 전부 이 값이다. `NOT FOUND` 면 설치가 안 된 것이니
사용자에게 README 의 설치 절차를 안내한다.

## 절차 — 지도 갱신

### 1. 추출 (항상)
```
python "$RM/extract.py" --map <지도>
```
새로 생기거나 커진 세션만 다시 digest 한다. 출력의 `*` 가 이번에 바뀐 세션이다.
`--all` 은 전체 재생성. 지도가 하나뿐이면 `--map` 은 생략 가능.
`--list-maps` 로 있는 지도를 본다.

출력 끝의 "다른 도구가 가져간 사본 N개"는 Codex 가 import 한 Claude 세션처럼 **같은 대화의
복사본**을 걸러낸 수다. 정상이다.

### 2. 카드 만들기 (바뀐 세션만)
바뀐 세션마다 서브에이전트(general-purpose, 백그라운드) 하나를 띄워 digest 를 읽고
`CARD_SCHEMA.md` 대로 `maps/<지도>/cards/<sid8>.json` 을 쓰게 한다. 프롬프트에 반드시 넣을 것:
- digest 경로, 카드 저장 경로, "CARD_SCHEMA.md 를 먼저 읽어라"
- 큰 digest(30만 자 이상)는 Read 의 offset/limit 으로 끝까지 나눠 읽으라고 명시 (뒤쪽이 중요)
- 한국어, 추정 금지, digest 에 있는 수치·경로·날짜만
- 같은 대화의 fork(시작 프롬프트·시각이 같은 세션)는 긴 쪽만 읽고 sessionIds 에 둘 다 넣기
- **다른 도구(Codex 등) 세션이면 그 사실과, 기존 지도와 겹치거나 어긋나는 부분을 짚으라고 지시**
서로 독립이므로 한 메시지에 여러 Agent 호출로 병렬 실행한다. 작은 세션은 3~4개씩 묶는다.

### 3. 지도 병합 (직접)
`MAP_SCHEMA.md` 를 읽는다. 기존 `map.json` 을 읽는다(없으면 새로 만든다).
카드 + config 의 `memoryDirs` 에 있는 메모리 파일(결론의 권위 있는 출처)을 읽고:
- 새 갈래 → 새 노드 (id 는 slug, 한번 정하면 불변)
- 기존 갈래의 진전 → 해당 노드의 `period.end`·`evidence`·`sources`·`next` 에 추가,
  필요하면 status 변경 + `detail` 에 `### 변경 이력`
- 철회·반증된 것은 지우지 않고 status 만 바꾼다
- result/process 노드에는 세션 출처를 반드시 단다 (`{"kind":"session","ref":"<full id>"}`)
- 산출 문서는 `artifact` 노드 또는 `sources` 의 `doc` 으로 — **경로는 실제 존재하는 것만**
- `next` 에 기한(`due`)·비용(`effort`)·막힘(`blockedBy`)이 **근거 있게** 드러나면 객체로 적는다.
  세션에 "약 4분", "11월 게이트", "X 가 나와야 시작" 같은 말이 있을 때만. 추측 금지 —
  안 적으면 접힌 목록으로 갈 뿐이고, 잘못 적으면 우선순위가 거짓말을 한다
`updatedAt` 을 오늘 날짜로.

### 4. 렌더 + 검증 + 열기
```
python "$RM/render.py" --map <지도> --open
```
사용자가 **페이지의 갱신 버튼**으로 부른 경우(`--serve` 서버가 실행) `--open` 없이 렌더한다.
버튼이 페이지를 알아서 새로고침한다.
ERROR 가 있으면 map.json 을 고친다. WARN(경로 없음, 인덱스에 없는 세션)도 가능하면 없앤다.

**`채울 곳:` 줄이 나오면 그냥 넘기지 마라.** 결과 노드에 근거 수치가 없다는 건 클릭해도
얻을 게 없다는 뜻이다. 그 노드의 출처 세션 digest·카드에서 수치를 찾아 `evidence` 에 넣고
다시 렌더한다. 정말 수치가 없는 갈래면 노드 종류를 `result` 가 아닌 `process` 로 고친다.
사용자는 페이지 상단 **채울 곳** 칩으로 같은 목록을 직접 볼 수 있다.

**변경 이력은 자동이다.** 렌더러가 직전 판과 비교해 달라진 게 있을 때만 리비전을 남기고,
`이번 판 rev N — 새 노드 a개 · 바뀐 노드 b개` 와 상태 뒤집힘 목록을 출력한다.
**그 출력을 그대로 사용자에게 보고한다** — 지도 전체를 다시 설명하지 말고 이번에 움직인 것만.
사용자는 페이지의 **변경** 탭에서 "지난 방문 이후" 를 따로 본다(브라우저에 마지막으로 본
리비전이 저장된다). 같은 지도를 다시 렌더해도 달라진 게 없으면 리비전은 안 쌓인다.
첫 렌더는 `기준선(rev1)` 이라 변경이 안 보이는 게 정상이다.

## 절차 — 새 지도 만들기

```
python "$RM/extract.py" --init <이름> --title "..." \
       [--source claude-code:~/.claude/projects] [--source codex:~/.codex/sessions] \
       [--source markdown:~/내보내기폴더]
```
그다음 `maps/<이름>/config.json` 의 `include` 로 그 연구에 해당하는 세션만 고른다.
같은 컴퓨터에서 여러 연구를 했다면 이 필터가 핵심이다.

| include 키 | 뜻 |
|---|---|
| `cwdContains` | 세션의 작업 폴더에 이 문자열이 있으면 포함 (예: `["projects/rat"]`) |
| `pathContains` | 기록 파일 경로로 거르기 |
| `since` / `until` | `"YYYY-MM-DD"` 기간 |
| `minPrompts` | 사용자 프롬프트가 이보다 적은 세션은 버림 |

**대화 하나만 담는 지도**는 `--session <id 일부>` 로 만든다(여러 번 줘도 된다).
기록 파일 이름에 id 가 들어가므로 어떤 소스든 통한다.

```
python "$RM/extract.py" --init <이름> --title "..." --session 9a34d5ca
```

### 연구가 아닌 세션 빼기

`config.json` 의 `exclude` 는 **사유와 함께** 뺀다. 그래야 지도에서 "빠뜨린 것"과
"일부러 뺀 것"이 구분된다.

```json
"exclude": {
  "sessions": {"96a87e86": "이 도구를 만든 세션 — 연구가 아님"},
  "firstPromptContains": ["[research-map:updater]"]
}
```

페이지의 갱신 버튼이 부른 실행은 프롬프트에 `[research-map:updater]` 가 찍혀 **자동으로
빠진다** — 안 그러면 갱신할 때마다 자기 실행 기록을 연구로 읽는다. 제외 규칙을 고치면
다음 `extract` 에서 이미 색인된 세션에도 다시 적용된다(`--all` 불필요).

`memoryDirs` 에는 그 연구의 메모리 폴더를 넣는다(지도의 `memory` 출처가 여기서 해석된다).

## 다른 LLM 기록 붙이기

| 종류 | 읽는 것 |
|---|---|
| `claude-code` | `~/.claude/projects/*/<sessionId>.jsonl` |
| `codex` | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (import 사본 자동 제외) |
| `markdown` | 폴더 안의 `.md` · `.txt` · `.json` — **다른 모든 LLM 용 범용 경로** |

ChatGPT·Gemini·Claude.ai 처럼 로컬 기록이 없는 도구는 대화를 내보내
markdown 소스 폴더에 파일로 넣으면 된다. `## User` / `## Assistant` 머리글이나
`{"messages":[{"role","content"}]}` JSON 이면 발화가 분리되고, 아니면 통째로 들어간다.

**새 도구를 정식 지원하려면** `rmlib.py` 에 `read_<kind>(root)` 제너레이터를 하나 쓰고
`SOURCES` 에 등록한다. `RawSession` 을 yield 하고 `add("user"|"assistant"|"tool"|"summary", ts, payload)`
만 부르면 나머지(digest·필터·증분·렌더)는 그대로 동작한다. 다른 파일은 건드리지 않는다.
`resumeCmd`(render.py)에 그 도구의 이어가기 명령을 넣으면 패널에 복사 버튼이 생긴다.

## 사용자가 자주 묻는 것 → 어디를 보나
- "내가 X 를 왜 접었지?" → 지도에서 X 검색 → status·`detail`의 변경 이력·출처 세션
- "다음에 뭘 파지?" → 탭 **열린 질문** — 기한·비용 있는 것이 위, 막힌 것은 아래, 미분류는 접힘
- "그 실험 언제 했지?" → 탭 **타임라인**
- "그때 대화 이어가기" → 노드 패널의 이어가기 명령 복사 버튼, 또는 탭 **세션**
- "지난번 이후 뭐가 바뀌었지?" → 탭 **변경** (헤더 배지 → 바뀐 곳만 지도에서 펼치기)
- "어디가 비어 있지?" → 헤더의 **채울 곳** 칩 (근거·출처·다음 단계가 빠진 노드만 남는다)

## 갱신 원칙
- 지도는 **누적**된다. 새로 만들 때마다 처음부터 쓰지 않는다.
- 노드 수가 150 을 넘으면 오래된 `process` 노드들을 상위 `result` 로 접어 요약한다.
- 사용자가 지도 내용을 정정하면 map.json 을 고치고 메모리에도 반영한다.
